#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Inspección geométrica PROPUESTA de miniaturas Edge AI, sin acceso a Cognex.

Instalar: python -m pip install "opencv-python-headless>=4.8,<5" numpy
Uso: python revisar_cajas.py --carpeta revisar_cajas
Demo y pruebas: python revisar_cajas.py --autoprueba
Ayuda completa: python revisar_cajas.py --guia

Solo lee PNG/CSV y escribe informes. Nunca modifica imágenes ni archivos .jobx.
Lo probado con sintéticos no valida la proyección, signos ni umbrales del L38.
"""
from __future__ import annotations

import argparse
import csv
import itertools
import json
import math
import re
import tempfile
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np

EDGES = ("arriba", "abajo", "izq", "der")
CONFIG_FIELDS = [
    "job", "celda", "lado", "referencia", "tam_x_mm", "tam_y_mm", "tam_z_mm",
    "ancho_proyeccion_px", "alto_proyeccion_px", "escala_validada", "modo",
    "fixture", "centro_fx_mm", "centro_fy_mm", "u_fx", "u_fy", "u_fz",
    "v_fx", "v_fy", "v_fz", "ejes_validados",
]
BASE_FIELDS = ["job", "celda", "dx_mm", "dy_mm", "dtheta_deg", "confianza",
               "negro_arriba", "negro_abajo", "negro_izq", "negro_der", "decision", "motivo"]

GUIDE = r"""
VERIFICADO EN DOCUMENTACION DE COGNEX
Ayuda EdgeAIClassify3D 26.2.0: Height Map mapea altura relativa al fondo a 0..255;
Feature Width puede rellenar huecos. Shape Change representa cambios de normales.
La ayuda NO acredita los signos de una miniatura capturada ni nuestros umbrales.
https://docs.cognex.com/isvs_2620/web/EN/InSight_Sheet3D/Content/Topics/Spreadsheet/3DVisionTools/EdgeAIClassify3D.htm
OpenCV documenta phaseCorrelate y findTransformECC (MOTION_EUCLIDEAN).
https://docs.opencv.org/4.x/d7/df3/group__imgproc__motion.html
https://docs.opencv.org/4.x/dc/d6b/group__video__track.html

SUPOSICIONES / POR PROBAR EN TUS PNG
- Mismo modo, parámetros de proyección, vista, escala y recorte para referencia
  y muestra. Crop simétrico respecto al centro físico de la proyección. No marcos,
  textos, márgenes internos ni reescalados distintos. Confirma esto manualmente.
- NEGRO <=22 es un indicador heurístico, no una máscara inequívoca de falta de
  puntos: altura válida baja también puede ser negra. No diagnostica el signo Z.
- Las mediciones describen el contenido referencia->muestra: +u derecha, +v abajo;
  theta positivo horario en pantalla. NO son automáticamente los ejes Cognex.
- dx_mm/dy_mm son componentes métricas u/v; dtheta_deg se mide tras normalizar
  píxeles anisótropos. Con escala ausente quedan vacíos; dx_px/dy_px y
  dtheta_imagen_deg conservan el resultado en coordenadas de imagen.
- La escala usa tam_x_mm/ancho_proyeccion_px y tam_y_mm/alto_proyeccion_px.
  Esas dimensiones son de la proyección MOSTRADA completa antes de recortar,
  no necesariamente la imagen nativa. Si quitaste 3 px de contenido por cada
  lado, ancho completo=ancho PNG+6. Si solo quitaste marco, NO sumar 6.
  Low/Medium/High no determina la escala de una captura redimensionada.
- Las dimensiones y ejes deben estar calibrados para propuestas físicas.
  En una COPIA del job/emulador, mueve solo el centro de una caja +X y luego +Y
  una cantidad conocida y observa el desplazamiento inverso del contenido;
  restaura cada valor y descarta la copia. Comprueba giro con un pequeño cambio
  conocido de rotación. Esto verifica signo y mm/px; no cambies tamaño/fixture.

CARPETAS Y CSV DE CONFIGURACION
revisar_cajas/cajas_config.csv: una fila por (job,celda). Primer arranque crea
una plantilla con campos vacíos si no existe: rellenar, no hay tamaños supuestos.
revisar_cajas/ref_LH_A20.png
revisar_cajas/pieza001/etiq_MI_JOB_A20.png
revisar_cajas/pieza002/etiq_MI_JOB_A20.png
La subcarpeta relativa es el ID de muestra: permite 15 nombres iguales sin
sobrescribir. El job admite guiones bajos, la celda debe ser del estilo A20.
En la raíz también se acepta un PNG, pero solo representa una muestra.
Ejecuta CAM1 y CAM2 en carpetas raíz separadas si reutilizan nombres de job/celda;
una subcarpeta cam1/cam2 no separa los resúmenes temporales por sí sola.
lado=LH/RH u otro valor exacto; referencia permite una ruta relativa explícita
por modelo y evita confundir referencias del mismo lado/celda entre modelos.
escala_validada=1 confirma escala/crop/misma proyección. Vacío/0 bloquea propuestas.
Los ejes u_f*,v_f* son vectores UNITARIOS, ortogonales, en coordenadas de fixture,
correspondientes al movimiento +u y +v del CONTENIDO. ejes_validados=1 confirma
su calibración. Ejemplo convencional (NO usar sin medir): u=(1,0,0),v=(0,-1,0).
Para este ajuste SE2 se exige u_fz=v_fz=0: cajas inclinadas requieren otro modelo.
centro_fx_mm,centro_fy_mm: centro de caja en fixture; fixture identifica el barrido.

ALGORITMO Y UMBRALES INICIALES (SUPOSICIONES)
- Señal pasaaltos suave; fase con ventana Hann y búsqueda de ángulos -5..5;
  ECC euclídeo multicomienzo y comprobación inversa independiente.
- Se mide desplazamiento EN EL CENTRO, no traslación del origen del warp.
- Calidad: NCC >=0.80, solapamiento >=0.60, confianza >=0.65, ciclo inverso <=1px.
  Confianza=NCC_positivo*sqrt(solapamiento); NO es probabilidad ni precisión mm.
  Respuesta de fase y ECC se exportan por separado. Mínima textura std gris>=5.
  Los umbrales deben calibrarse con buenos/malos de tu proceso, no con yield SAT.
- Giro >1 grado, desplazamiento >2mm o >10% del campo visible: REVISAR.
  La fracción relativa sigue funcionando si falta escala física.
- Negro por borde: porcentaje de una banda interior (15% del ancho/alto)
  perteneciente a componentes negros conectados a ESE borde, conectividad8.
  Se calcula sobre PNG original, SIN alinearlo. Un componente puede contar en
  varios bordes: los porcentajes NO se suman. Delta>=15 PUNTOS: REVISAR.
  Este denominador puede diferir de corte.py: recalibrar o igualar definiciones.
- Movimiento grande: REVISAR; puede haber candidata si es estable y confiable.
  Poco solapamiento o alineación ambigua: REVISAR, sin propuesta.
  ECC/fase no garantizan resolver ambigüedades en patrones repetidos.

AGREGACION Y PROPUESTAS
Con --muestras-sincronizadas confirmas que las carpetas representan el MISMO frame
físico entre herramientas: NO basta el ordinal de miniatura. Agrupa por job,
fixture y muestra. Cambia solamente el informe, no el equipo.
Convierte d_i = [u v] (dx_mm,dy_mm); ajusta q_i=c_i+d_i=R*c_i+t mediante
RANSAC+Huber, mínimo4 y >=60% de herramientas geométricamente válidas, separación
>=30mm. Este consenso no distingue pieza movida de PatMax incorrecto. Para eso
se necesitan registros PatMax y referencia mecánica independiente.
fixture_resultado.csv informa ajuste y residuos por muestra. Un residuo aislado
es candidato a problema local/registro, no prueba de caja mal posicionada.
resumen_herramientas.csv informa mediana/MAD sobre muestras y residuos respecto
al consenso. Usa suelo1mm/0.3deg y umbral3.5*sigma_MAD para outliers.
No descarta automáticamente frames: un desplazamiento real puede ser válido.
No se propone corrección fija si hay dispersión temporal, pérdidas de cobertura,
alineaciones fallidas o metadatos incompletos. Se requieren las15 muestras esperadas
(--muestras-esperadas permite cambiarlo, mínimo10 para propuestas) y todas fiables.
Con sincronía también se verifica la unión de IDs entre herramientas del fixture.
Los resúmenes NO convierten 15 frames en validación SAT.
propuestas_centros.csv contiene solo DELTAS a revisar en copia: centro X/Y del
fixture y giro alrededor de +Z de fixture. La rotación NO es directamente el
argumento Rot de Cognex; requiere la conversión 3D validada por vosotros.
Si contenido se desplazó +X, seguirlo con la caja requiere +X. El warp para
alinear la imagen a la referencia usa el inverso: no confundir ambos signos.
Z queda vacío/NO_IDENTIFICABLE; no se automatiza el ajuste empírico +3mm.
Incluso Height Map no separa de forma fiable falta de puntos, alturas bajas y
truncamiento Z con estos PNG. Shape Change no es una escala de altura.

CAMBIO, RIESGO, VERIFICACION Y REVERSION
Cambio: genera mediciones e hipótesis; no manda comandos Cognex/PLC/cámaras.
Riesgo: falsa alineación o escala/orientación errónea. Verificación: --autoprueba,
después contrastar ejemplos reales y pequeños cambios conocidos solo en copia.
Reversión: borrar los CSV generados; los PNG y jobs permanecen intactos. Cualquier
ensayo posterior en In-Sight se revierte restaurando valores o descartando copia.
"""


def read_png(path):
    """imdecode soporta rutas Unicode de Windows."""
    image = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_UNCHANGED)
    if image is None or image.ndim != 2 or image.dtype != np.uint8:
        raise ValueError("PNG_NO_ES_GRIS_8_BITS")
    if min(image.shape) < 32:
        raise ValueError("MINIATURA_MENOR_32PX")
    return image


def write_csv(path, rows, fields=None):
    if fields is None:
        fields = list(dict.fromkeys(k for row in rows for k in row if not k.startswith("_")))
    if not fields:
        fields = ["estado"]
    with Path(path).open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            clean = {}
            for k in fields:
                value = row.get(k, "")
                if isinstance(value, (float, np.floating)):
                    value = round(float(value), 6) if np.isfinite(value) else ""
                clean[k] = value
            writer.writerow(clean)


def number(row, name):
    try:
        value = float(row.get(name, ""))
        return value if np.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def border_black(image, threshold=22, band_fraction=0.15):
    """Porcentaje de banda negra conectada a cada borde; no suma a 100%."""
    mask = np.ascontiguousarray(image <= threshold, dtype=np.uint8)
    count, labels = cv2.connectedComponents(mask, connectivity=8)
    h, w = image.shape
    by, bx = max(1, round(h * band_fraction)), max(1, round(w * band_fraction))
    seeds = [labels[0], labels[-1], labels[:, 0], labels[:, -1]]
    bands = [labels[:by], labels[-by:], labels[:, :bx], labels[:, -bx:]]
    out = {}
    for edge, seed, band in zip(EDGES, seeds, bands):
        touching = np.zeros(count, dtype=bool)
        touching[np.unique(seed)] = True
        touching[0] = False
        out[edge] = 100.0 * float(touching[band].mean())
    return out


def _signal(image):
    f = image.astype(np.float32) / 255.0
    f = cv2.GaussianBlur(f, (0, 0), 0.8)
    f = f - cv2.GaussianBlur(f, (0, 0), 6.0)
    return f / max(float(f.std()), 0.005)


def repetition_score(image):
    """Busca autocoincidencias lejanas de una ventana central (heurística)."""
    signal = _signal(image)
    h, w = signal.shape
    x, y = w//4, h//4
    template = signal[y:y+h//2, x:x+w//2].copy()
    if float(template.std()) < 0.05:
        return 1.0
    scores = cv2.matchTemplate(signal, template, cv2.TM_CCOEFF_NORMED)
    yy, xx = np.indices(scores.shape)
    distance = np.hypot(xx-x, yy-y)
    scores[distance < max(6, min(h, w)*0.05)] = -1
    return float(np.nanmax(scores))


def _rotation_at_center(shape, theta):
    h, w = shape
    center = np.array([(w - 1) / 2.0, (h - 1) / 2.0])
    angle = math.radians(theta)
    r = np.array([[math.cos(angle), -math.sin(angle)],
                  [math.sin(angle), math.cos(angle)]], dtype=np.float32)
    return np.column_stack([r, center - r @ center]).astype(np.float32)


def _alignment_quality(ref, sample, matrix, threshold):
    h, w = ref.shape
    flags = cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP
    aligned = cv2.warpAffine(sample, matrix, (w, h), flags=flags)
    inside = cv2.warpAffine(np.ones_like(sample, dtype=np.uint8), matrix, (w, h),
                            flags=cv2.INTER_NEAREST | cv2.WARP_INVERSE_MAP) > 0
    ref_valid = ref > threshold
    moved_valid = cv2.warpAffine((sample > threshold).astype(np.uint8), matrix, (w, h),
                                flags=cv2.INTER_NEAREST | cv2.WARP_INVERSE_MAP) > 0
    common = ref_valid & moved_valid & inside
    overlap = float(common.sum()) / max(int(ref_valid.sum()), int((sample > threshold).sum()), 1)
    common = cv2.erode(common.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
    if common.sum() < 100:
        return -1.0, overlap
    a, b = ref[common].astype(float), aligned[common].astype(float)
    a -= a.mean()
    b -= b.mean()
    norm = np.linalg.norm(a) * np.linalg.norm(b)
    ncc = float(a @ b / norm) if norm > 1e-8 else -1.0
    return ncc, overlap


def _estimate_one_way(ref, sample, threshold, max_angle):
    a, b = _signal(ref), _signal(sample)
    h, w = a.shape
    hann = cv2.createHanningWindow((w, h), cv2.CV_32F)
    seeds = []
    for angle in np.linspace(-max_angle, max_angle, 11):
        matrix = _rotation_at_center(a.shape, angle)
        rotated = cv2.warpAffine(a, matrix, (w, h))
        (dx, dy), response = cv2.phaseCorrelate(rotated.copy(), b.copy(), hann)
        if not np.isfinite([dx, dy, response]).all():
            continue
        matrix[:, 2] += [dx, dy]
        ncc, overlap = _alignment_quality(ref, sample, matrix, threshold)
        seeds.append((max(ncc, 0) * math.sqrt(overlap), matrix, float(response)))
    if not seeds:
        raise ValueError("FASE_SIN_RESULTADO")
    seeds.sort(key=lambda item: item[0], reverse=True)
    candidates = []
    for _, initial, response in seeds[:4]:
        matrix = initial.copy()
        try:
            ecc, matrix = cv2.findTransformECC(a, b, matrix, cv2.MOTION_EUCLIDEAN,
                (cv2.TERM_CRITERIA_COUNT | cv2.TERM_CRITERIA_EPS, 90, 1e-5), None, 5)
        except cv2.error:
            continue
        theta = math.degrees(math.atan2(matrix[1, 0], matrix[0, 0]))
        if not np.isfinite(matrix).all() or abs(theta) > max_angle + 0.25:
            continue
        ncc, overlap = _alignment_quality(ref, sample, matrix, threshold)
        score = max(ncc, 0) * math.sqrt(overlap)
        candidates.append(dict(matrix=matrix, theta=theta, ncc=ncc, overlap=overlap,
                               confidence=score, phase_response=response, ecc=float(ecc)))
    if not candidates:
        raise ValueError("ECC_NO_CONVERGE_O_GIRO_FUERA_RANGO")
    candidates.sort(key=lambda x: x["confidence"], reverse=True)
    best = candidates[0]
    best["ambiguous"] = False
    center = np.array([(w - 1) / 2, (h - 1) / 2, 1.0])
    for other in candidates[1:]:
        distance = np.linalg.norm((best["matrix"] - other["matrix"]) @ center)
        if (best["confidence"] - other["confidence"] < 0.02
                and (distance > 2.0 or abs(best["theta"] - other["theta"]) > 0.7)):
            best["ambiguous"] = True
    return best


def align_images(ref, sample, sx=None, sy=None, threshold=22, max_angle=5.0):
    """Transformación referencia->muestra; desplazamiento evaluado en centro.

    sx,sy: mm por pixel en u,v. Si faltan, solo geometría de imagen (unidad px).
    """
    if ref.shape != sample.shape:
        raise ValueError("TAMANOS_PNG_DISTINTOS_NO_REESCALAR_A_CIEGAS")
    if min(float(ref.std()), float(sample.std())) < 5.0:
        raise ValueError("TEXTURA_INSUFICIENTE")
    if min(np.mean(ref > threshold), np.mean(sample > threshold)) < 0.15:
        raise ValueError("MUY_POCO_CONTENIDO_NO_NEGRO")
    sx, sy = (1.0, 1.0) if sx is None or sy is None else (sx, sy)
    h, w = ref.shape
    unit = max(sx, sy, w * sx / 512, h * sy / 512)
    scales = np.array([sx / unit, sy / unit])
    size = (int(math.ceil((w - 1) * scales[0])) + 1,
            int(math.ceil((h - 1) * scales[1])) + 1)
    if min(size) < 24:
        raise ValueError("RESOLUCION_METRICA_INSUFICIENTE")
    rescale = np.array([[scales[0], 0, 0], [0, scales[1], 0]], np.float32)
    a = cv2.warpAffine(ref, rescale, size)
    b = cv2.warpAffine(sample, rescale, size)
    best = _estimate_one_way(a, b, threshold, max_angle)
    inverse = _estimate_one_way(b, a, threshold, max_angle)
    forward3 = np.vstack([best["matrix"], [0, 0, 1]])
    inverse3 = np.vstack([inverse["matrix"], [0, 0, 1]])
    points = np.array([[0, 0, 1], [size[0]-1, 0, 1], [0, size[1]-1, 1],
                       [size[0]-1, size[1]-1, 1]], float).T
    cycle = (inverse3 @ forward3 @ points - points)[:2]
    best["cycle_px"] = float(np.max(np.linalg.norm(cycle / scales[:, None], axis=0)))
    center = np.array([(w-1)/2 * scales[0], (h-1)/2 * scales[1], 1.0])
    displacement_work = best["matrix"] @ center - center[:2]
    best["dx_px"], best["dy_px"] = (displacement_work / scales).tolist()
    best["du"], best["dv"] = (displacement_work * unit).tolist()
    original_matrix = np.diag(1/scales) @ best["matrix"][:, :2] @ np.diag(scales)
    best["theta_image"] = math.degrees(math.atan2(original_matrix[1, 0], original_matrix[0, 0]))
    best["ambiguous"] = best["ambiguous"] or inverse["ambiguous"]
    best["repetition"] = max(repetition_score(a), repetition_score(b))
    if best["repetition"] >= 0.96:
        best["ambiguous"] = True
    best["reliable"] = bool(best["ncc"] >= 0.80 and best["overlap"] >= 0.60
        and best["confidence"] >= 0.65 and best["cycle_px"] <= 1.0
        and not best["ambiguous"] and abs(best["theta"]) < max_angle - 0.1)
    return best


def metric_scale(config, shape):
    fields = [number(config, x) for x in ("tam_x_mm", "tam_y_mm", "ancho_proyeccion_px", "alto_proyeccion_px")]
    if any(v is None or v <= 0 for v in fields):
        return None, None
    tx, ty, full_w, full_h = fields
    if full_w < shape[1] or full_h < shape[0]:
        raise ValueError("PROYECCION_COMPLETA_MENOR_QUE_PNG")
    return tx/full_w, ty/full_h


def fixture_geometry(config):
    """Solo bases ortonormales en XY; nunca interpreta ángulos Cognex."""
    if config.get("ejes_validados") != "1" or config.get("escala_validada") != "1":
        return None
    vals = [number(config, k) for k in ("u_fx", "u_fy", "u_fz", "v_fx", "v_fy", "v_fz",
                                       "centro_fx_mm", "centro_fy_mm")]
    if any(v is None for v in vals) or not config.get("fixture"):
        return None
    u, v = np.array(vals[:3]), np.array(vals[3:6])
    if not np.allclose(np.array([u, v]) @ np.array([u, v]).T, np.eye(2), atol=0.01):
        return None
    if max(abs(u[2]), abs(v[2])) > 1e-5:
        return None
    return np.column_stack([u[:2], v[:2]]), np.array(vals[6:])


def analyze_pair(ref, sample, config, args):
    reference_black = border_black(ref, args.negro, args.banda)
    sample_black = border_black(sample, args.negro, args.banda)
    out, reasons = {}, []
    for edge in EDGES:
        out["negro_" + edge] = sample_black[edge]
        out["ref_negro_" + edge] = reference_black[edge]
        delta = sample_black[edge] - reference_black[edge]
        out["delta_negro_" + edge + "_pp"] = delta
        if delta >= args.delta_negro:
            reasons.append("NEGRO_BORDE_" + edge.upper())
    out["_border_issue"] = bool(reasons)
    sx, sy = metric_scale(config, ref.shape)
    if sx is None:
        reasons.append("FALTA_ESCALA_MM")
    elif config.get("escala_validada") != "1":
        reasons.append("ESCALA_POR_VALIDAR")
    try:
        alignment = align_images(ref, sample, sx, sy, args.negro, args.max_giro)
    except (ValueError, cv2.error) as exc:
        out.update({"decision": "REVISAR", "motivo": ";".join(reasons + [str(exc)]),
                    "confianza": 0.0, "_reliable": False})
        return out
    out.update({"dx_px": alignment["dx_px"], "dy_px": alignment["dy_px"],
                "dx_mm": alignment["du"] if sx else "", "dy_mm": alignment["dv"] if sy else "",
                "dtheta_deg": alignment["theta"] if sx else "",
                "dtheta_imagen_deg": alignment["theta_image"], "confianza": alignment["confidence"],
                "ncc": alignment["ncc"], "solapamiento": alignment["overlap"],
                "respuesta_fase": alignment["phase_response"], "ecc": alignment["ecc"],
                "autocoincidencia_textura": alignment["repetition"],
                "error_ciclo_px": alignment["cycle_px"], "_reliable": alignment["reliable"],
                "mm_por_px_u": sx if sx else "", "mm_por_px_v": sy if sy else ""})
    if not alignment["reliable"]:
        reasons.append("ALINEACION_NO_CONFIABLE")
    if alignment["ambiguous"]:
        reasons.append("ALINEACION_AMBIGUA")
    if abs(alignment["theta"]) > args.giro_revision:
        reasons.append("GIRO_SUPERA_UMBRAL")
    h, w = ref.shape
    if max(abs(alignment["dx_px"])/w, abs(alignment["dy_px"])/h) > args.fraccion_desplazamiento:
        reasons.append("DESPLAZAMIENTO_RELATIVO_GRANDE")
    if sx and math.hypot(alignment["du"], alignment["dv"]) > args.desplazamiento_mm:
        reasons.append("DESPLAZAMIENTO_MM_SUPERA_UMBRAL")
    geom = fixture_geometry(config)
    if geom is not None and alignment["reliable"] and sx:
        basis, center = geom
        shift = basis @ [alignment["du"], alignment["dv"]]
        out.update({"_fixture_shift": shift, "_center": center,
                    "_fixture_theta": float(np.sign(np.linalg.det(basis)) * alignment["theta"]),
                    "dx_fixture_mm": shift[0], "dy_fixture_mm": shift[1]})
    out["decision"] = "REVISAR" if reasons else "OK"
    out["motivo"] = ";".join(reasons) if reasons else "SIN_ALERTAS_GEOMETRICAS"
    return out


def discover(root):
    found = []
    pattern = re.compile(r"^etiq_(.+)_([A-Za-z]+[0-9]+)\.png$", re.IGNORECASE)
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        match = pattern.match(path.name)
        if match:
            found.append((path, match[1], match[2].upper(), path.parent.relative_to(root).as_posix()))
    return found


def load_config(path, samples):
    if not path.exists():
        rows = [dict(job=j, celda=c) for j, c in sorted({(j, c) for _, j, c, _ in samples})]
        write_csv(path, rows, CONFIG_FIELDS)
        print("Plantilla creada; completa dimensiones, referencia y calibración:", path)
        return {}
    with path.open(encoding="utf-8-sig", newline="") as f:
        result = {}
        for row in csv.DictReader(f):
            key = row["job"], row["celda"].upper()
            if key in result:
                raise ValueError("CONFIG_DUPLICADA: " + repr(key))
            result[key] = row
        return result


def resolve_reference(root, cfg, cell):
    if cfg.get("referencia"):
        return root / cfg["referencia"]
    if cfg.get("lado"):
        return root / ("ref_" + cfg["lado"] + "_" + cell + ".png")
    raise ValueError("FALTA_LADO_O_REFERENCIA_EXPLICITA")


def add_reason(row, reason):
    if row.get("motivo") == "SIN_ALERTAS_GEOMETRICAS":
        row["motivo"] = reason
    else:
        row["motivo"] = (row.get("motivo", "") + ";" + reason).strip(";")
    row["decision"] = "REVISAR"



def wrap_degrees(values):
    """Ángulos en [-180, 180), conservando arrays y escalares numpy."""
    return (np.asarray(values, dtype=float) + 180.0) % 360.0 - 180.0


def _weighted_rigid_2d(p, q, weights):
    weights = np.asarray(weights, float)
    total = float(weights.sum())
    if total <= 0:
        raise ValueError("Pesos sin soporte")
    w = weights / total
    cp = np.sum(p * w[:, None], axis=0)
    cq = np.sum(q * w[:, None], axis=0)
    a, b = p - cp, q - cq
    u, _, vt = np.linalg.svd(a.T @ (w[:, None] * b))
    correction = np.eye(2)
    correction[1, 1] = np.linalg.det(vt.T @ u.T)
    r = vt.T @ correction @ u.T
    return r, cq - r @ cp


def _max_baseline(points):
    if len(points) < 2:
        return 0.0
    return float(np.sqrt(np.max(np.sum(
        (points[:, None, :] - points[None, :, :]) ** 2, axis=2))))


def fit_fixture_rigid(centers, shifts, weights=None, rotations_deg=None,
                      seed=12345, residual_threshold_mm=2.0,
                      min_inliers=None, min_baseline_mm=30.0,
                      huber_delta_mm=1.0, max_trials=1000):
    """RANSAC de pares y Procrustes ponderado con refinamiento Huber.

    Cada shift debe medir desplazamiento referencia->muestra, convertido primero
    a los ejes comunes del fixture. Los centros deben pertenecer al MISMO frame,
    barrido, fixture y plano compatible. Esta función no puede verificarlo.

    rotations_deg es opcional y sirve de contraste: no impone el giro del ajuste.
    Un movimiento común no permite distinguir movimiento de pieza de error PatMax.
    """
    p_all = np.asarray(centers, dtype=float)
    d_all = np.asarray(shifts, dtype=float)
    if p_all.ndim != 2 or p_all.shape[1] != 2 or d_all.shape != p_all.shape:
        raise ValueError("centers y shifts deben tener forma Nx2")
    n_all = len(p_all)
    w_all = np.ones(n_all) if weights is None else np.asarray(weights, float)
    if w_all.shape != (n_all,):
        raise ValueError("weights debe tener N elementos")
    angles_all = None
    if rotations_deg is not None:
        angles_all = np.asarray(rotations_deg, float)
        if angles_all.shape != (n_all,):
            raise ValueError("rotations_deg debe tener N elementos")
    if residual_threshold_mm <= 0 or min_baseline_mm <= 0 or huber_delta_mm <= 0:
        raise ValueError("Los umbrales geométricos deben ser positivos")
    finite = (np.isfinite(p_all).all(axis=1) & np.isfinite(d_all).all(axis=1)
              & np.isfinite(w_all) & (w_all > 0))
    indices = np.flatnonzero(finite)
    p, q, w = p_all[finite], (p_all + d_all)[finite], w_all[finite]
    n = len(p)
    # Nunca permitir que una minoría de herramientas defina el movimiento común.
    required = max(4, int(math.ceil(0.6 * n)),
                   0 if min_inliers is None else int(min_inliers))
    result = {
        "success": False, "reason": "", "tx_mm": float("nan"),
        "ty_mm": float("nan"), "theta_deg": float("nan"),
        "residuals_mm": [float("nan")] * n_all, "inliers": [False] * n_all,
        "valid_count": n, "inlier_count": 0, "required_inliers": required,
        "baseline_mm": _max_baseline(p), "rms_inlier_mm": float("nan"),
        "coverage_axis_ratio": float("nan"), "warnings": [],
        "rotation_residuals_deg": [float("nan")] * n_all,
    }
    if n < required:
        result["reason"] = "MUESTRAS_COMUNES_INSUFICIENTES"
        return result
    if result["baseline_mm"] < min_baseline_mm:
        result["reason"] = "BASELINE_INSUFICIENTE_PARA_GIRO"
        return result
    w = w / max(float(w.max()), 1e-12)
    pairs = list(itertools.combinations(range(n), 2))
    if len(pairs) > max_trials:
        rng = np.random.default_rng(seed)
        selected = rng.choice(len(pairs), max_trials, replace=False)
        pairs = [pairs[int(i)] for i in selected]
    best = None
    for i, j in pairs:
        if np.linalg.norm(p[j] - p[i]) < min_baseline_mm:
            continue
        if np.linalg.norm(q[j] - q[i]) < 1e-9:
            continue
        r, t = _weighted_rigid_2d(p[[i, j]], q[[i, j]], w[[i, j]])
        residual = np.linalg.norm(q - (p @ r.T + t), axis=1)
        mask = residual <= residual_threshold_mm
        count = int(mask.sum())
        if count < required or _max_baseline(p[mask]) < min_baseline_mm:
            continue
        score = (float(w[mask].sum()), count, -float(np.mean(residual[mask])))
        if best is None or score > best[0]:
            best = (score, r, t, mask)
    if best is None:
        result["reason"] = "SIN_CONSENSO_RIGIDO"
        return result
    _, r, t, mask = best
    for _ in range(30):
        residual = np.linalg.norm(q - (p @ r.T + t), axis=1)
        huber = np.minimum(1.0, huber_delta_mm / np.maximum(residual, 1e-12))
        effective = w * huber * mask
        nr, nt = _weighted_rigid_2d(p, q, effective)
        nr_residual = np.linalg.norm(q - (p @ nr.T + nt), axis=1)
        new_mask = nr_residual <= residual_threshold_mm
        if int(new_mask.sum()) < required or _max_baseline(p[new_mask]) < min_baseline_mm:
            break
        change = np.linalg.norm(nt - t) + np.linalg.norm(nr - r)
        same_mask = np.array_equal(mask, new_mask)
        r, t, mask = nr, nt, new_mask
        if change < 1e-9 and same_mask:
            break
    residual = np.linalg.norm(q - (p @ r.T + t), axis=1)
    mask = residual <= residual_threshold_mm
    theta = float(wrap_degrees(np.degrees(np.arctan2(r[1, 0], r[0, 0]))))
    residual_full = np.full(n_all, np.nan)
    inlier_full = np.zeros(n_all, dtype=bool)
    residual_full[indices], inlier_full[indices] = residual, mask
    centered = p[mask] - np.average(p[mask], axis=0, weights=w[mask])
    eigenvalues = np.linalg.eigvalsh(centered.T @ (w[mask, None] * centered))
    ratio = float(np.sqrt(max(eigenvalues[0], 0) / max(eigenvalues[1], 1e-12)))
    warnings = []
    if ratio < 0.1:
        warnings.append("COBERTURA_CASI_LINEAL: extrapolacion fuera de la zona poco respaldada")
    if angles_all is not None:
        angle_residual = wrap_degrees(angles_all - theta)
        result["rotation_residuals_deg"] = angle_residual.tolist()
        valid_angles = inlier_full & np.isfinite(angle_residual)
        if valid_angles.any() and np.median(np.abs(angle_residual[valid_angles])) > 1.0:
            warnings.append("GIROS_LOCALES_DISCREPAN: comprobar ejes, signos y alineacion")
    result.update({
        "success": int(mask.sum()) >= required,
        "reason": "CONSENSO_RIGIDO_OBSERVADO",
        "tx_mm": float(t[0]), "ty_mm": float(t[1]), "theta_deg": theta,
        "residuals_mm": residual_full.tolist(), "inliers": inlier_full.tolist(),
        "inlier_count": int(mask.sum()), "baseline_mm": _max_baseline(p[mask]),
        "rms_inlier_mm": float(np.sqrt(np.average(residual[mask] ** 2, weights=w[mask]))),
        "coverage_axis_ratio": ratio, "warnings": warnings,
    })
    return result


def robust_temporal_stats(values, z_limit=3.5, floor_mm=1.0,
                          floor_deg=0.3, stable_translation_mm=2.0,
                          stable_angle_deg=0.7, minimum_samples=5):
    """Mediana/MAD de Nx3 (dx_mm, dy_mm, giro_deg), con ángulos circulares.

    Umbral por eje = max(suelo absoluto, z_limit * 1.4826 * MAD).
    P90 y máximos incluyen TODOS los frames válidos, también los outliers:
    un único deslizamiento grande bloquea una propuesta de corrección fija.
    No identifica causalidad ni sustituye una revisión de los frames atípicos.
    """
    x = np.asarray(values, dtype=float)
    if x.ndim != 2 or x.shape[1] != 3:
        raise ValueError("values debe tener forma Nx3")
    finite = np.isfinite(x).all(axis=1)
    a = x[finite].copy()
    base = {
        "count": len(a), "median": [float("nan")] * 3,
        "mad": [float("nan")] * 3, "robust_sigma": [float("nan")] * 3,
        "thresholds": [float("nan")] * 3,
        "outliers": (~finite).tolist(), "outlier_count": int((~finite).sum()),
        "p90_translation_mm": float("nan"), "p90_angle_deg": float("nan"),
        "max_translation_mm": float("nan"), "max_angle_deg": float("nan"),
        "stable_for_fixed_correction": False, "reason": "SIN_DATOS_VALIDOS",
    }
    if not len(a):
        return base
    anchor = float(a[0, 2])
    a[:, 2] = anchor + wrap_degrees(a[:, 2] - anchor)
    median = np.median(a, axis=0)
    differences = a - median
    differences[:, 2] = wrap_degrees(differences[:, 2])
    mad = np.median(np.abs(differences), axis=0)
    sigma = 1.4826 * mad
    thresholds = np.maximum(z_limit * sigma, [floor_mm, floor_mm, floor_deg])
    flags = np.any(np.abs(differences) > thresholds, axis=1)
    all_flags = ~finite
    all_flags[finite] = flags
    translations = np.linalg.norm(differences[:, :2], axis=1)
    angles = np.abs(differences[:, 2])
    p90_translation = float(np.percentile(translations, 90))
    p90_angle = float(np.percentile(angles, 90))
    max_translation = float(np.max(translations))
    max_angle = float(np.max(angles))
    stable = (len(a) >= minimum_samples and p90_translation <= stable_translation_mm
              and p90_angle <= stable_angle_deg
              and max_translation <= 2.0 * stable_translation_mm
              and max_angle <= 2.0 * stable_angle_deg)
    median[2] = wrap_degrees(median[2])
    reason = "ESTABLE_EN_MUESTRAS" if stable else "DISPERSION_NO_PROPONER_CORRECCION_FIJA"
    if len(a) < minimum_samples:
        reason = "MUESTRAS_INSUFICIENTES_PARA_ESTABILIDAD"
    base.update({
        "median": median.tolist(), "mad": mad.tolist(),
        "robust_sigma": sigma.tolist(), "thresholds": thresholds.tolist(),
        "outliers": all_flags.tolist(), "outlier_count": int(all_flags.sum()),
        "p90_translation_mm": p90_translation, "p90_angle_deg": p90_angle,
        "max_translation_mm": max_translation, "max_angle_deg": max_angle,
        "stable_for_fixed_correction": stable, "reason": reason,
    })
    return base


def selftest_fixture_helpers():
    rng = np.random.default_rng(214)
    p = rng.uniform([-200, -80], [200, 80], (19, 2))
    theta = np.radians(3.0)
    r = np.array([[np.cos(theta), -np.sin(theta)], [np.sin(theta), np.cos(theta)]])
    q = p @ r.T + [20.0, -12.0] + rng.normal(0, 0.08, p.shape)
    q[[1, 4, 7, 10]] += [[12, 8], [-15, 20], [25, -10], [8, 14]]
    fit = fit_fixture_rigid(p, q - p, np.ones(19))
    assert fit["success"], fit
    assert abs(fit["tx_mm"] - 20) < 0.1, fit
    assert abs(fit["ty_mm"] + 12) < 0.1, fit
    assert abs(fit["theta_deg"] - 3) < 0.05, fit
    assert fit["inlier_count"] == 15, fit
    invalid = fit_fixture_rigid(np.zeros((5, 2)), np.ones((5, 2)))
    assert not invalid["success"], invalid
    moving = np.column_stack([np.linspace(0, 20, 15), np.zeros(15), np.zeros(15)])
    summary = robust_temporal_stats(moving)
    assert not summary["stable_for_fixed_correction"], summary
    single_slip = np.zeros((15, 3))
    single_slip[-1, 0] = 20.0
    one_slip_summary = robust_temporal_stats(single_slip)
    assert one_slip_summary["p90_translation_mm"] == 0.0, one_slip_summary
    assert one_slip_summary["max_translation_mm"] == 20.0, one_slip_summary
    assert not one_slip_summary["stable_for_fixed_correction"], one_slip_summary
    single_angle = np.zeros((15, 3))
    single_angle[-1, 2] = 5.0
    one_angle_summary = robust_temporal_stats(single_angle)
    assert not one_angle_summary["stable_for_fixed_correction"], one_angle_summary
    wrapped = np.array([[0, 0, 179.9], [0.01, 0, -179.9], [0, 0, 179.8],
                        [0, 0, -179.8], [0, 0, 179.95], [10, 0, 170]])
    summary2 = robust_temporal_stats(wrapped)
    assert summary2["outliers"][-1], summary2
    assert abs(abs(summary2["median"][2]) - 180) < 0.2, summary2
    return {"rigid": fit, "moving_p90_mm": summary["p90_translation_mm"],
            "single_slip_max_mm": one_slip_summary["max_translation_mm"],
            "temporal_wrap_outliers": summary2["outlier_count"]}


def aggregate(rows, configs, args):
    """Consenso por frame primero; resumen temporal después."""
    fixture_rows, summaries, proposals = [], [], []
    grouped = defaultdict(list)
    expected_ids = defaultdict(set)
    for row in rows:
        expected_ids[(row["job"], row.get("fixture", ""))].add(row["muestra"])
    if args.muestras_sincronizadas:
        for row in rows:
            if row.get("fixture"):
                grouped[(row["job"], row["fixture"], row["muestra"])].append(row)
        for (job, fixture, sample_id), members in grouped.items():
            usable = [r for r in members if "_fixture_shift" in r]
            expected = sum(1 for (j, _), cfg in configs.items()
                if j == job and cfg.get("fixture") == fixture and fixture_geometry(cfg) is not None)
            report = dict(job=job, fixture=fixture, muestra=sample_id,
                          herramientas_esperadas=expected, herramientas_utilizables=len(usable))
            if len(usable) < 4:
                report.update(estado="SIN_DATOS_GEOMETRICOS_SUFICIENTES", motivo="MINIMO_4_Y_EJES_XY_VALIDADOS")
                fixture_rows.append(report)
                continue
            fit = fit_fixture_rigid([r["_center"] for r in usable],
                    [r["_fixture_shift"] for r in usable], [r["confianza"]**2 for r in usable],
                    [r["_fixture_theta"] for r in usable],
                    min_inliers=max(4, math.ceil(expected * 0.6)),
                    residual_threshold_mm=args.residuo_fixture_mm,
                    min_baseline_mm=args.separacion_mm)
            report.update({"estado": fit["reason"], "tx_mm": fit["tx_mm"], "ty_mm": fit["ty_mm"],
                           "theta_fixture_deg": fit["theta_deg"], "inliers": fit["inlier_count"],
                           "rms_mm": fit["rms_inlier_mm"], "separacion_mm": fit["baseline_mm"],
                           "avisos": ";".join(fit["warnings"])})
            fixture_rows.append(report)
            if not fit["success"]:
                continue
            angle = math.radians(fit["theta_deg"])
            rotation = np.array([[math.cos(angle), -math.sin(angle)], [math.sin(angle), math.cos(angle)]])
            translation = np.array([fit["tx_mm"], fit["ty_mm"]])
            for index, row in enumerate(usable):
                common = rotation @ row["_center"] + translation - row["_center"]
                residual = row["_fixture_shift"] - common
                angle_residual = float(wrap_degrees(row["_fixture_theta"] - fit["theta_deg"]))
                row.update({"comun_dx_fixture_mm": common[0], "comun_dy_fixture_mm": common[1],
                            "comun_theta_fixture_deg": fit["theta_deg"],
                            "residuo_local_x_mm": residual[0], "residuo_local_y_mm": residual[1],
                            "residuo_local_theta_deg": angle_residual,
                            "residuo_local_mm": fit["residuals_mm"][index],
                            "consenso_fixture": int(fit["inliers"][index]),
                            "_residual": np.array([residual[0], residual[1], angle_residual])})
                if not fit["inliers"][index] or abs(angle_residual) > args.giro_revision:
                    add_reason(row, "DISCREPANCIA_LOCAL_FRENTE_A_CONSENSO")

    per_tool = defaultdict(list)
    for row in rows:
        per_tool[(row["job"], row["celda"])].append(row)
    for (job, cell), members in per_tool.items():
        usable = [r for r in members if r.get("_reliable") and number(r, "dx_mm") is not None]
        summary = dict(job=job, celda=cell, muestras=len(members), alineaciones_confiables=len(usable))
        if not usable:
            summary["estado"] = "SIN_MEDICIONES_METRICAS_CONFIABLES"
            summaries.append(summary)
            continue
        stats = robust_temporal_stats([[r["dx_mm"], r["dy_mm"], r["dtheta_deg"]] for r in usable],
                                      minimum_samples=10)
        for row, outlier in zip(usable, stats["outliers"]):
            row["outlier_temporal"] = int(outlier)
            if outlier:
                add_reason(row, "OUTLIER_TEMPORAL_NO_DESCARTAR_AUTOMATICAMENTE")
        summary.update({"mediana_dx_mm": stats["median"][0], "mediana_dy_mm": stats["median"][1],
                        "mediana_theta_deg": stats["median"][2], "mad_dx_mm": stats["mad"][0],
                        "mad_dy_mm": stats["mad"][1], "mad_theta_deg": stats["mad"][2],
                        "outliers": stats["outlier_count"], "p90_dispersion_mm": stats["p90_translation_mm"],
                        "max_dispersion_mm": stats["max_translation_mm"],
                        "p90_dispersion_deg": stats["p90_angle_deg"], "estado": stats["reason"]})
        residual_rows = [r for r in usable if "_residual" in r]
        if residual_rows:
            local = robust_temporal_stats([r["_residual"] for r in residual_rows], minimum_samples=10)
            summary.update({"mediana_residuo_local_x_mm": local["median"][0],
                            "mediana_residuo_local_y_mm": local["median"][1],
                            "mediana_residuo_local_theta_deg": local["median"][2],
                            "residuo_local_estable": int(local["stable_for_fixed_correction"])})
        summaries.append(summary)
        geometry_rows = [r for r in usable if "_fixture_shift" in r]
        frame_ids = {r["muestra"] for r in members}
        fixture_id = members[0].get("fixture", "")
        missing_ids = expected_ids[(job, fixture_id)] - frame_ids if args.muestras_sincronizadas else set()
        summary["muestras_esperadas_minimo"] = args.muestras_esperadas
        summary["muestras_ausentes_conocidas"] = ";".join(sorted(missing_ids))
        proposal = dict(job=job, celda=cell, delta_centro_fx_mm="", delta_centro_fy_mm="",
                        delta_centro_fz_mm="", delta_giro_fixture_deg="", z_estado="NO_IDENTIFICABLE",
                        estado="NO_PROPONER", motivo="METADATOS_O_ESTABILIDAD_INSUFICIENTES")
        enough = (len(geometry_rows) >= max(10, args.muestras_esperadas)
                  and len(geometry_rows) == len(members) and not missing_ids)
        if len(geometry_rows) < len(members):
            proposal["motivo"] = "COBERTURA_TEMPORAL_O_GEOMETRIA_INCOMPLETA"
        if missing_ids or len(members) < args.muestras_esperadas:
            proposal["motivo"] = "MUESTRAS_AUSENTES_O_MENOS_QUE_LAS_ESPERADAS"
        if enough:
            physical = robust_temporal_stats([[*r["_fixture_shift"], r["_fixture_theta"]]
                                             for r in geometry_rows], minimum_samples=10)
            if stats["stable_for_fixed_correction"] and physical["stable_for_fixed_correction"]:
                dx, dy, angle = physical["median"]
                if math.hypot(dx, dy) < 0.5 and abs(angle) < 0.3:
                    proposal.update(estado="SIN_AJUSTE_SIGNIFICATIVO", motivo="SESGO_MENOR_0.5MM_Y_0.3DEG")
                else:
                    proposal.update(delta_centro_fx_mm=dx, delta_centro_fy_mm=dy,
                                    delta_giro_fixture_deg=angle, estado="CANDIDATA_REVISAR_EN_COPIA",
                                    motivo="SESGO_ESTABLE;NO_GARANTIZA_CORREGIR_BORDES_O_Z;NO_ES_ROT_COGNEX")
            else:
                proposal["motivo"] = "MOVIMIENTO_VARIABLE_NO_CORREGIR_CON_UNA_MEDIANA_FIJA"
        proposals.append(proposal)
    return fixture_rows, summaries, proposals


def run_folder(args):
    root = Path(args.carpeta).resolve()
    if not root.is_dir():
        raise ValueError("No existe la carpeta: " + str(root))
    samples = discover(root)
    if not samples:
        raise ValueError("No hay PNG etiq_<job>_<celda>.png en " + str(root))
    identities = [(j, c, frame) for _, j, c, frame in samples]
    if len(set(identities)) != len(identities):
        raise ValueError("IDENTIDAD_DUPLICADA_JOB_CELDA_MUESTRA")
    config_path = Path(args.config).resolve() if args.config else root / "cajas_config.csv"
    configs = load_config(config_path, samples)
    output = Path(args.salida).resolve() if args.salida else root
    output.mkdir(parents=True, exist_ok=True)
    results, cache = [], {}
    for index, (path, job, cell, sample_id) in enumerate(samples):
        cfg = configs.get((job, cell), {})
        row = dict(job=job, celda=cell, muestra=sample_id, archivo=str(path.relative_to(root)),
                   fixture=cfg.get("fixture", ""), modo=cfg.get("modo", ""))
        try:
            ref_path = resolve_reference(root, cfg, cell).resolve()
            row["referencia"] = str(ref_path)
            if ref_path not in cache:
                cache[ref_path] = read_png(ref_path)
            sample = read_png(path)
            row.update(analyze_pair(cache[ref_path], sample, cfg, args))
        except (ValueError, OSError, cv2.error) as exc:
            row.update(decision="REVISAR", motivo=str(exc), confianza=0.0, _reliable=False)
        results.append(row)
        if (index + 1) % 25 == 0:
            print("Procesadas", index + 1, "de", len(samples), flush=True)
    fixture, summaries, proposals = aggregate(results, configs, args)
    extras = list(dict.fromkeys(k for r in results for k in r if not k.startswith("_") and k not in BASE_FIELDS))
    write_csv(output / "regiones_resultado.csv", results, BASE_FIELDS + extras)
    write_csv(output / "fixture_resultado.csv", fixture or [{"estado": "SIN_AJUSTE_COMUN",
        "motivo": "REQUIERE_SINCRONIA_EXPLICITA_GEOMETRIA_Y_MINIMO_4_HERRAMIENTAS"}])
    write_csv(output / "resumen_herramientas.csv", summaries)
    write_csv(output / "propuestas_centros.csv", proposals or [{"estado": "SIN_PROPUESTAS"}])
    metadata = {"opencv": cv2.__version__, "numpy": np.__version__, "parametros": vars(args),
                "convencion": "referencia->muestra; u derecha,v abajo,theta horario; Z no identificable",
                "umbral_estado": "PROPUESTOS_NO_VALIDADOS_EN_COGNEX",
                "png_procesados": len(results), "revisar": sum(r["decision"] == "REVISAR" for r in results)}
    (output / "ejecucion_parametros.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    print("Resultado:", output / "regiones_resultado.csv", "| PNG:", len(results),
          "| REVISAR:", metadata["revisar"], flush=True)
    return results, fixture, summaries, proposals


def synthetic_texture(seed=42, height=128, width=160):
    rng = np.random.default_rng(seed)
    image = np.clip(cv2.GaussianBlur(rng.normal(125, 45, (height, width)).astype(np.float32),
                                    (0, 0), 1.2), 25, 235).astype(np.uint8)
    for _ in range(35):
        x, y = rng.integers([8, 8], [width-8, height-8])
        cv2.circle(image, (int(x), int(y)), int(rng.integers(2, 8)), int(rng.integers(30, 240)), -1)
    return image


def synthetic_warp(image, dx, dy, angle, sx=1.0, sy=1.0):
    """Movimiento físico; dx/dy en píxeles originales, ángulo en plano métrico."""
    h, w = image.shape
    rad = math.radians(angle)
    rotation = np.array([[math.cos(rad), -math.sin(rad)], [math.sin(rad), math.cos(rad)]])
    matrix2 = np.diag([1/sx, 1/sy]) @ rotation @ np.diag([sx, sy])
    center = np.array([(w-1)/2, (h-1)/2])
    matrix = np.column_stack([matrix2, center - matrix2 @ center + [dx, dy]])
    return cv2.warpAffine(image, matrix, (w, h))


def selftest_aggregation():
    """Comprueba que datos ausentes o fallidos no autorizan ajustes fijos."""
    args = build_parser().parse_args([])
    def cfg(center):
        return dict(escala_validada="1", ejes_validados="1", fixture="B1",
            centro_fx_mm=str(center[0]), centro_fy_mm=str(center[1]),
            u_fx="1", u_fy="0", u_fz="0", v_fx="0", v_fy="1", v_fz="0")
    def row(cell, frame, center, delta=(3., 0.), reliable=True):
        value = dict(job="J", celda=cell, muestra="p%02d" % frame, fixture="B1",
            dx_mm=delta[0], dy_mm=delta[1], dtheta_deg=0., confianza=.95,
            decision="REVISAR", motivo="DESPLAZAMIENTO", _reliable=reliable)
        if reliable:
            value.update(_fixture_shift=np.array(delta), _fixture_theta=0., _center=np.array(center))
        return value
    config = {("J", "A20"): cfg((0., 0.))}
    frames = [row("A20", i, (0., 0.), reliable=i < 14) for i in range(15)]
    _, _, proposals = aggregate(frames, config, args)
    assert proposals[0]["estado"] == "NO_PROPONER", proposals
    frames = [row("A20", i, (0., 0.), delta=(20., 0.) if i == 14 else (3., 0.)) for i in range(15)]
    _, _, proposals = aggregate(frames, config, args)
    assert proposals[0]["estado"] == "NO_PROPONER", proposals
    centers = np.array([(x*40., y*40.) for x in range(4) for y in range(5)])[:19]
    configs = {("J", "A%d" % (20+i)): cfg(c) for i, c in enumerate(centers)}
    args.muestras_sincronizadas = True
    for count, should_fit in [(11, False), (12, True)]:
        frames = [row("A%d" % (20+i), 0, c) for i, c in enumerate(centers[:count])]
        fits, _, _ = aggregate(frames, configs, args)
        assert (fits[0]["estado"] == "CONSENSO_RIGIDO_OBSERVADO") == should_fit, fits
    # 14 PNG frente a15 de las demás herramientas: la unión detecta la omisión,
    # incluso reduciendo explícitamente el mínimo solicitado a14.
    args.muestras_esperadas = 14
    frames = [row("A%d" % (20+i), frame, c)
              for i, c in enumerate(centers) for frame in range(15)
              if not (i == 0 and frame == 14)]
    _, summaries, proposals = aggregate(frames, configs, args)
    proposal = next(p for p in proposals if p["celda"] == "A20")
    summary = next(s for s in summaries if s["celda"] == "A20")
    assert proposal["estado"] == "NO_PROPONER", proposal
    assert summary["muestras_ausentes_conocidas"] == "p14", summary
    return ["frame_fallido_bloquea_ajuste", "deslizamiento20_bloquea_ajuste",
            "consenso_minimo60_por_ciento", "png_ausente_detectado_por_union_ids"]


def selftest():
    """Pruebas deterministas, sin imágenes del usuario; falla con AssertionError."""
    records = []
    reference = synthetic_texture()
    cases = [("identica", 0, 0, 0, .5, .5), ("traslacion", 7, -4, 0, .5, .5),
             ("giro_positivo", 5, -3, 3, .5, .5), ("giro_negativo", -10, 6, -4, .5, .5),
             ("anisotropia", 6, -4, 3, .4, .7)]
    for name, dx, dy, theta, sx, sy in cases:
        sample = synthetic_warp(reference, dx, dy, theta, sx, sy)
        result = align_images(reference, sample, sx, sy)
        assert result["reliable"], (name, result)
        error_px = math.hypot(result["dx_px"] - dx, result["dy_px"] - dy)
        error_deg = abs(result["theta"] - theta)
        assert error_px < 0.4 and error_deg < 0.2, (name, result)
        records.append(dict(caso=name, error_px=error_px, error_deg=error_deg, confianza=result["confidence"]))
    sample = synthetic_warp(reference, 5, -3, 2)
    noise = np.random.default_rng(11).normal(0, 1.5, sample.shape)
    sample = np.clip(sample.astype(float) * 0.85 + 10 + noise, 0, 255).astype(np.uint8)
    result = align_images(reference, sample, .5, .5)
    assert result["reliable"] and abs(result["dx_px"] - 5) < .4, result
    records.append(dict(caso="contraste_ruido", confianza=result["confidence"]))
    flat = np.full_like(reference, 120)
    for name, image in [("plana", flat), ("negra", np.zeros_like(flat))]:
        try:
            align_images(image, image, .5, .5)
            raise AssertionError("Se aceptó " + name)
        except ValueError:
            records.append(dict(caso=name, estado="RECHAZADA"))
    unrelated = synthetic_texture(seed=830)
    try:
        result = align_images(reference, unrelated, .5, .5)
        assert not result["reliable"], result
    except ValueError:
        pass
    records.append(dict(caso="no_correspondencia", estado="RECHAZADA"))
    vv, uu = np.indices((128, 192))
    periodic = np.clip(125+50*np.cos(2*np.pi*uu/16)+30*np.cos(2*np.pi*vv/16), 0, 255).astype(np.uint8)
    repeat_result = align_images(periodic, np.roll(periodic, 23, axis=1), .5, .5)
    assert not repeat_result["reliable"] and repeat_result["ambiguous"], repeat_result
    records.append(dict(caso="periodica_alias23_vs7", estado="AMBIGUA_RECHAZADA"))
    black = np.full((100, 100), 100, np.uint8)
    black[:5] = 0
    borders = border_black(black)
    assert abs(borders["arriba"] - 100/3) < .001 and borders["abajo"] == 0, borders
    hole = np.full((100, 100), 100, np.uint8)
    hole[20:40, 20:40] = 0
    assert max(border_black(hole).values()) == 0
    cfg = dict(tam_x_mm="83", tam_y_mm="67", ancho_proyeccion_px="166", alto_proyeccion_px="134")
    assert metric_scale(cfg, reference.shape) == (.5, .5)
    # Bases con reflexión: imagen horario positivo -> fixture antihorario negativo.
    cfg.update(escala_validada="1", ejes_validados="1", fixture="B1", centro_fx_mm="0", centro_fy_mm="0",
               u_fx="1", u_fy="0", u_fz="0", v_fx="0", v_fy="-1", v_fz="0")
    basis, _ = fixture_geometry(cfg)
    assert np.allclose(basis @ [2, 3], [2, -3]) and np.linalg.det(basis) < 0
    cfg["u_fz"] = "0.1"
    assert fixture_geometry(cfg) is None
    helpers = selftest_fixture_helpers()
    records.append(dict(caso="geometria_robusta", tx=helpers["rigid"]["tx_mm"],
                        ty=helpers["rigid"]["ty_mm"], theta=helpers["rigid"]["theta_deg"]))
    records.append(dict(caso="un_deslizamiento_entre15", max_mm=helpers["single_slip_max_mm"], estado="SIN_CORRECCION_FIJA"))
    records.extend(dict(caso=name, estado="APROBADA") for name in selftest_aggregation())
    # Prueba de nombres, CSV, escala y main sin depender de ficheros externos.
    with tempfile.TemporaryDirectory(prefix="cajas_sinteticas_") as folder:
        root = Path(folder)
        (root / "m001").mkdir()
        cv2.imencode(".png", reference)[1].tofile(str(root / "ref_LH_A20.png"))
        cv2.imencode(".png", reference)[1].tofile(str(root / "m001" / "etiq_JOB_CON_GUIONES_A20.png"))
        write_csv(root / "cajas_config.csv", [dict(job="JOB_CON_GUIONES", celda="A20", lado="LH",
                  tam_x_mm=80, tam_y_mm=64, ancho_proyeccion_px=160, alto_proyeccion_px=128,
                  escala_validada=1)], CONFIG_FIELDS)
        args = build_parser().parse_args(["--carpeta", str(root)])
        rows, _, _, _ = run_folder(args)
        assert len(rows) == 1 and rows[0]["decision"] == "OK", rows
        with (root / "regiones_resultado.csv").open(encoding="utf-8-sig") as f:
            saved = list(csv.DictReader(f))
        assert saved[0]["muestra"] == "m001" and saved[0]["job"] == "JOB_CON_GUIONES"
    print(json.dumps({"pruebas": records, "estado": "APROBADAS_SOLO_SINTETICOS",
                      "opencv": cv2.__version__, "numpy": np.__version__}, indent=2, ensure_ascii=False))


def create_demo(folder):
    """19 herramientas x15 frames; tres cajas con residuo local persistente."""
    root = Path(folder).resolve()
    if root.exists():
        raise ValueError("La carpeta demo ya existe; no se sobrescribe: " + str(root))
    root.mkdir(parents=True)
    rng = np.random.default_rng(41)
    centers = rng.uniform([-160, -70], [160, 70], (19, 2))
    configs = []
    for tool, center in enumerate(centers):
        cell = "A" + str(20 + tool)
        ref = synthetic_texture(seed=tool + 80)
        cv2.imencode(".png", ref)[1].tofile(str(root / ("ref_LH_" + cell + ".png")))
        configs.append(dict(job="DEMO_LH", celda=cell, lado="LH", tam_x_mm=80, tam_y_mm=64,
            tam_z_mm=30, ancho_proyeccion_px=160, alto_proyeccion_px=128, escala_validada=1,
            fixture="B1", modo="SINTETICO", centro_fx_mm=center[0], centro_fy_mm=center[1],
            u_fx=1, u_fy=0, u_fz=0, v_fx=0, v_fy=1, v_fz=0, ejes_validados=1))
        for frame in range(15):
            directory = root / ("pieza%03d" % frame)
            directory.mkdir(exist_ok=True)
            theta = 1.2 + .08 * math.sin(frame)
            rad = math.radians(theta)
            rot = np.array([[math.cos(rad), -math.sin(rad)], [math.sin(rad), math.cos(rad)]])
            delta = rot @ center - center + [2.5 + .08 * math.sin(frame), -1.5]
            if tool in (2, 7, 13):
                delta += [3.5, -1.5]
            sample = synthetic_warp(ref, delta[0]/.5, delta[1]/.5, theta)
            cv2.imencode(".png", sample)[1].tofile(str(directory / ("etiq_DEMO_LH_" + cell + ".png")))
    write_csv(root / "cajas_config.csv", configs, CONFIG_FIELDS)
    print("Demo creada:", root, "(285 PNG de muestras +19 referencias)")


def build_parser():
    parser = argparse.ArgumentParser(description="Revisa PNG Edge AI; solo informes, sin conexiones Cognex.")
    parser.add_argument("--carpeta", default="revisar_cajas")
    parser.add_argument("--config", help="CSV de metadatos; predeterminado carpeta/cajas_config.csv")
    parser.add_argument("--salida", help="Carpeta de informes; predeterminado carpeta de entrada")
    parser.add_argument("--muestras-sincronizadas", action="store_true", help="Confirma mismo frame físico por subcarpeta")
    parser.add_argument("--muestras-esperadas", type=int, default=15, help="Mínimo previsto por herramienta para propuestas")
    parser.add_argument("--negro", type=int, default=22)
    parser.add_argument("--banda", type=float, default=.15)
    parser.add_argument("--delta-negro", type=float, default=15)
    parser.add_argument("--max-giro", type=float, default=5)
    parser.add_argument("--giro-revision", type=float, default=1)
    parser.add_argument("--desplazamiento-mm", type=float, default=2)
    parser.add_argument("--fraccion-desplazamiento", type=float, default=.10)
    parser.add_argument("--residuo-fixture-mm", type=float, default=2)
    parser.add_argument("--separacion-mm", type=float, default=30)
    parser.add_argument("--autoprueba", action="store_true")
    parser.add_argument("--crear-demo", metavar="CARPETA_NUEVA")
    parser.add_argument("--guia", action="store_true")
    return parser


def main():
    args = build_parser().parse_args()
    if args.guia:
        print(GUIDE)
        return
    if args.autoprueba:
        selftest()
        return
    if args.crear_demo:
        create_demo(args.crear_demo)
        return
    if not (0 <= args.negro <= 254 and 0 < args.banda <= .5 and 0 < args.max_giro <= 10
            and args.delta_negro > 0 and args.giro_revision > 0 and args.desplazamiento_mm > 0
            and args.fraccion_desplazamiento > 0 and args.residuo_fixture_mm > 0 and args.separacion_mm > 0
            and args.muestras_esperadas > 0):
        raise ValueError("Umbrales fuera de rango")
    run_folder(args)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError) as error:
        raise SystemExit("ERROR: " + str(error))


