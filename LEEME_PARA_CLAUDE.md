# Entrega técnica a Claude Code — Cognex L38 / Edge AI 3D

Fecha de entrega: 29 de octubre de 2026, America/Mexico_City.
Preparado por ChatGPT/Codex a petición del usuario. El brief original abarca pruebas reportadas del 29–30 de octubre; esa fecha del brief no constituye evidencia de nuevas pruebas ejecutadas aquí.

## 1. Qué contiene y qué está terminado

Se entrega un analizador de miniaturas en un único `revisar_cajas.py`, una guía de ejecución para Windows PowerShell 5.1, pruebas sintéticas reproducibles y el contrato HMI aportado por el usuario. El script es autocontenido: solo requiere Python, numpy y OpenCV; no necesita `fixture_helpers.py` ni `audit_tests.py`.

El analizador implementa registro de imágenes, métricas de negro en bordes, conversión métrica condicionada a metadatos, consenso entre herramientas, análisis temporal y propuestas de corrección revisables. No contiene cliente HMI, UIA ni comunicación con dispositivos.

**Pendiente principal HMI:** no se recibió el resultado del sondeo `beginEdit` sobre una `EdgeAIClassify3D`. No afirmar que el entrenador 3D por API funciona o que no existe.

## 2. Evidencia: mantener estas categorías separadas

### Verificado en documentación de Cognex

1. Cognex publica ejemplos de apertura de sesión y login mediante CogSocket/WebSocket. Esto respalda parte del protocolo, no un entrenador 3D completo. [Fuente oficial](https://support.cognex.com/en/help-articles/web-sdk-how-to-open-session-via-websocket).
2. Cognex documenta `setCellValue` con celda y valor; el artículo consultado se refiere a IS2800/IS3800. No extrapolar todas sus capacidades al emulador L38. [Fuente oficial](https://support.cognex.com/en/help-articles/in-sight-how-to-change-cell-value-via-websocket-cogsocket).
3. La ayuda 26.2.0 de `EdgeAIClassify3D` describe recopilación desde filmstrip, etiquetado gráfico y mínimo cinco imágenes por clase. Height Map representa alturas relativas al fondo en 0–255 y puede rellenar huecos según Feature Width; Shape Change representa cambios de normales. No acredita los signos de las miniaturas capturadas ni un método para decidir Z a partir de negro. [Ayuda consultada](https://docs.cognex.com/isvs_2620/web/EN/InSight_Sheet3D/Content/Topics/Spreadsheet/3DVisionTools/EdgeAIClassify3D.htm).

La instalación del usuario es **26.2.1**. La página 3D 26.2.1 no pudo consultarse con la herramienta web; no presentar la ayuda 26.2.0 como comprobación completa de esa versión.

### Documentación de OpenCV, distinta de documentación Cognex

Se consultaron las funciones oficiales `phaseCorrelate` y `findTransformECC`, incluido el modelo euclídeo. La búsqueda de ángulos, combinación de métricas, umbrales, detección de repetición y controles temporales son diseño de este script, no recomendaciones de Cognex.

- [Correlación de fase](https://docs.opencv.org/4.x/d7/df3/group__imgproc__motion.html)
- [ECC y modelos de movimiento](https://docs.opencv.org/4.x/dc/d6b/group__video__track.html)

### Evidencia aportada por el usuario, no reproducida aquí

- Dos L38-100, Vision Suite 26.2.1, 60 jobs, 30 modelos; cam1 dos barridos y cam2 tres. Cada barrido usa PatMax/Fixture y 18–19 clasificadores.
- Cliente HMI y casillas funcionando en el emulador; servidor local descubierto en `sheetsPortRegistry.json`; comportamiento de sesiones, trigger offline y filmstrip descrito en el brief.
- Contrato del entrenador extraído de `chunk-BX2FP2EY.js` y `main-WLNLH57I.js` del HMI beta instalado. Los fragmentos fueron pegados por el usuario; no se inspeccionaron aquí esos archivos originales.
- UIA sobre miniaturas mediante Select/Invoke provoca fallos; UIA de lectura, selección de celdas y clics físicos son el flujo actual. La latencia UIA y los tiempos de entrenamiento provienen de mediciones del usuario.
- `.jobx` firmado, errores al modificarlo externamente y pérdida del entrenamiento al cambiar tamaño/fixture: restricciones y observaciones del proyecto, sin investigación independiente del formato en esta entrega.
- Convención angular medida por el equipo: `R = Rz(Direccion) Ry(Inclinacion) Rz(Rotacion-Direccion)`. El script entregado NO la implementa ni la sustituye: recibe bases de ejes ya calibradas.
- ISPROD-15691, ISPROD-8923 y CVE-2025-54810 fueron citados en el brief. No se verificaron sus detalles o alcance en esta investigación; no añadir conclusiones de seguridad/compatibilidad basadas solo en sus identificadores.

### Probado aquí

Solo imágenes sintéticas y archivos generados en este entorno. No se recibieron miniaturas reales ni logs del servidor Cognex. Las pruebas se ejecutaron en Linux con Python 3.12, OpenCV 4.14.0 y numpy 2.3.5; no se ejecutó el script en Windows ni en In-Sight. Las versiones exactas se registran con los resultados.

## 3. Restricciones del trabajo

- Solo emulador, sobre copia respaldada. Nunca cámaras reales ni PLC.
- Nunca modificar ni reconstruir `.jobx` fuera de In-Sight.
- Nunca cambiar tamaño ni referencia de fixture de Edge AI como parte de una corrección.
- Las propuestas de este paquete son datos para revisión; no deben aplicarse automáticamente.
- No entrenar deep learning propio. Todo el análisis entregado es geometría, correlación y estadística clásica.
- No se requiere conexión HMI para ejecutar el analizador de PNG.

## 4. HMI: resultado de la revisión

El contrato completo está en `CONTRATO_HMI_OBSERVADO.md`. Las correcciones importantes ya adoptadas por el usuario son:

- `beginEdit` manda una cadena; la hipótesis anterior de array fue corregida.
- `apply`/`cancel` cuelgan de la URL de edición, no de `toolEditor`.
- `getSamples` es una composición del cliente, no una ruta demostrada.
- El cliente llama a `train` después de etiquetar. No se ha demostrado entrenamiento implícito del servidor al llamar solamente a `setClassLabel`.
- Ausencia de editor significa «no obtenido en esta celda/condiciones», no ausencia universal de soporte 3D.
- El sondeo abre una edición, aunque no escriba etiquetas: no se llama «solo lectura».

El usuario informó que su script ya tiene inventario de etiquetas exactas, comparación de IDs/cantidades, metadatos de muestra, conteos repetidos, JSON con profundidad20, comparación exacta de tipo y cancelación registrada en `finally`. Ante timeout de `beginEdit`: estado desconocido, sin reintento ni `cancel`/`endEdit` especulativos; descartar la copia y resolver el estado del editor por el flujo conocido.

El `endEdit` de la rama de edición normal se conserva cuando no hay entrenador, según el flujo observado por el usuario. Nunca se agrega después de `cancel` por rutina. Un cancelado sin cambios no demuestra rollback de etiquetas entrenadas.

No se incluyen versiones inventadas de `hmi_comun.ps1` o `hmi_beginedit_prueba.ps1`: sus archivos completos no fueron aportados a ChatGPT.

## 5. Analizador de cajas: funcionamiento

1. Lee pares PNG grises de8 bits y rechaza tamaños distintos o imágenes insuficientes.
2. Usa señal pasaaltos suave, ventana Hann y correlación de fase con semillas de giro entre -5° y +5°.
3. Refina mediante ECC euclídeo con varios comienzos. Comprueba correlación tras alineación, solapamiento, consistencia de la transformación inversa y autocoincidencias alejadas indicativas de periodicidad.
4. Mide desplazamiento en el **centro de la proyección**. Los términos de traslación del origen de la matriz no son el desplazamiento correcto del centro cuando existe giro.
5. Calcula negro conectado a cada borde sobre las imágenes originales, sin alinear ni esconder el corte.
6. Con metadatos, expresa desplazamientos en mm; con ejes validados, los convierte a XY del fixture.
7. Con sincronía explícita, ajusta movimiento común por frame mediante RANSAC y refinamiento Huber.
8. Resume por herramienta con mediana/MAD, amplitud y outliers, sin borrar muestras.

### Escala y signos

`dx_mm = dx_px * TamX / ancho_proyeccion_completa_px`, análogo para Y.

La dimensión completa corresponde a la proyección MOSTRADA antes de recortar; no necesariamente a la resolución nativa. Sumar6 al ancho PNG solo cuando se quitaron exactamente3 píxeles de contenido por cada lado. Si se quitó marco o margen, esa suma puede ser incorrecta. Low/Medium/High no reconstruye por sí solo la escala de una captura redimensionada.

Convención del resultado: referencia→muestra, u positivo derecha, v positivo abajo, giro positivo horario en imagen. La escala anisótropa se normaliza antes de medir el giro métrico. `dx_mm`/`dy_mm` son componentes métricas en u/v, no automáticamente X/Y de Cognex.

La conversión a fixture usa vectores unitarios u/v calibrados. El modelo común implementado exige ejes contenidos en XY del fixture; no resuelve cajas inclinadas ni estima movimiento 3D completo. El giro resultante alrededor de Z del fixture no debe escribirse directamente al argumento Rot de Cognex.

Si el contenido se desplazó +X respecto a la referencia, una caja que lo siga se desplaza +X. La transformación de imagen para regresar la muestra a la referencia utiliza el sentido inverso.

### Negro y Z

Umbral inicial negro<=22, aportado por el usuario. Por cada borde se calcula la fracción de una banda interior de15% que pertenece a componentes negros conectados a ese borde, conectividad8. Los cuatro porcentajes pueden contar el mismo componente y no suman100%.

**No se verificó el denominador de `corte.py`**: si ese script usa toda el área, estos porcentajes no son comparables sin adaptar la definición. El incremento de15 puntos porcentuales conserva el criterio inicial del usuario, pero necesita calibración con la misma métrica.

Negro puede significar altura válida baja, falta de puntos o truncamiento lateral/vertical. Z queda vacío como `NO_IDENTIFICABLE`. No se automatiza el ajuste empírico +3mm ni se interpreta Shape Change como altura.

### Movimiento común y local

Con centros `c_i` y desplazamientos expresados en el fixture `d_i`, se ajusta:

`c_i + d_i = R(theta) c_i + t`.

Se exige mínimo4 herramientas, al menos60% de las herramientas geométricamente elegibles configuradas y separación espacial mínima30mm. Los residuos indican discrepancia local, que puede ser caja, pieza, defecto o registro incorrecto: no es un diagnóstico causal.

La identidad de frame tiene que ser física. El ordinal de la miniatura puede diferir entre herramientas por omisiones u ordenación. El consenso no distingue error PatMax de movimiento real sin otra evidencia.

### Propuestas y cobertura temporal

Predeterminado:15 muestras esperadas. Se bloquean propuestas fijas si falta una medición confiable, falta geometría, hay menos muestras esperadas, se detectan IDs ausentes al comparar herramientas sincronizadas, o la dispersión supera los criterios. Se consideran máximos además de percentiles para que un único deslizamiento grande no quede oculto.

Un desplazamiento grande pero estable y confiable puede generar una **candidata para revisar**, no una aprobación de ajuste. Los valores propuestos son deltas de centro XY y giro en fixture. No incluyen tamaño, fixture nuevo ni Z.

## 6. Umbrales iniciales: suposición, no especificación Cognex

| Medida | Valor inicial | Motivo y límite |
|---|---:|---|
| Negro | <=22 | Dato empírico del usuario; también puede incluir altura válida baja |
| Banda del borde | 15% | Detectar pérdida de cobertura cercana al borde; denominador nuevo |
| Incremento negro | >=15 puntos | Criterio inicial aportado, requiere comparación con corte.py |
| Correlación NCC | >=0.80 | Exige correspondencia visual razonable; no garantiza unicidad |
| Solapamiento | >=0.60 | Evita extrapolar con muy poco contenido común |
| Confianza | >=0.65 | NCC positiva por raíz del solapamiento; no es probabilidad |
| Error ida/vuelta | <=1px | Detecta inconsistencia de registros; no elimina alias periódicos |
| Autocoincidencia lejana | >=0.96 => ambigua | Heurística conservadora; puede marcar texturas repetidas o poco discriminantes |
| Giro para revisión | >1° | Alerta inicial ajustable; búsqueda predeterminada ±5° |
| Desplazamiento | >2mm o >10% del campo | Alerta geométrica, no tolerancia de producto validada |
| Residuo común | 2mm | Umbral RANSAC inicial, debe adaptarse a la precisión real |
| Outlier temporal | max(suelo,3.5×1.4826×MAD) | Suelos1mm/0.3°; marca, no descarta automáticamente |

Los umbrales no prueban yield, desempeño SAT ni clasificación OK/NOK. «OK» en `regiones_resultado.csv` significa ausencia de alertas geométricas según estos criterios.

## 7. Archivos, configuración y ejecución

Usar Python3 y PowerShell5.1. No se utiliza `&&` ni operador ternario de PowerShell.

```powershell
python -m pip install -r .\requirements.txt
python .\revisar_cajas.py --autoprueba
python .\revisar_cajas.py --guia
python .\revisar_cajas.py --carpeta .\revisar_cajas
```

El primer recorrido crea `cajas_config.csv` vacío por herramienta si no existe. Rellenarlo antes de interpretar resultados físicos. No confundir la plantilla con una configuración validada. Puede usarse `ejemplo_cajas_config.csv` como referencia de columnas; sus valores son exclusivamente sintéticos.

Estructura:

- `revisar_cajas/ref_LH_A20.png`
- `revisar_cajas/pieza001/etiq_MI_JOB_A20.png`
- `revisar_cajas/pieza002/etiq_MI_JOB_A20.png`

Las subcarpetas permiten conservar15 muestras con el mismo nombre base. `referencia` en el CSV permite una ruta explícita por modelo. CAM1 y CAM2 deben ejecutarse en raíces separadas si reutilizan job/celda.

Para agrupar frames cuya identidad física ya se haya confirmado:

```powershell
python .\revisar_cajas.py --carpeta .\revisar_cajas --muestras-sincronizadas
```

Para crear y analizar sintéticos sin imágenes del usuario:

```powershell
python .\revisar_cajas.py --crear-demo .\demo_local_nueva
python .\revisar_cajas.py --carpeta .\demo_local_nueva --muestras-sincronizadas
```

La carpeta demo debe ser nueva; el generador se niega a sobrescribirla. `validar_paquete.ps1` también ejecuta autopruebas y, opcionalmente con `-Demo`, crea una demo nueva. Ese lanzador se revisó para sintaxis5.1, pero no se ejecutó en Windows en esta sesión.

Salidas:

- `regiones_resultado.csv`: columnas solicitadas por el usuario más muestra, referencia, negro de referencia/deltas, métricas de alineación y residuos de consenso.
- `fixture_resultado.csv`: ajuste común por muestra, consenso y RMS agregado.
- `resumen_herramientas.csv`: medianas, MAD, dispersión y cobertura temporal.
- `propuestas_centros.csv`: candidatas o motivos de bloqueo; Z vacío.
- `ejecucion_parametros.json`: versión de librerías y parámetros de esa ejecución.

## 8. Resultados sintéticos incluidos

Las autopruebas y la demo se volvieron a ejecutar con el script que se entrega. Ver `resultados_verificados/` y `demo_sintetica/`.

- Casos básicos de registro: error máximo observado0.1231px y0.1062°; no equivalen a precisión Cognex.
- Test geométrico independiente,19 herramientas/4 outliers: movimiento real (20,-12)mm/3°, estimado (20.0245,-11.9955)mm/3.00954°,15 inliers.
- Demo integrada:19 herramientas×15 muestras,285 pares más19 referencias. Las tres herramientas alteradas son A22/A27/A33.
- Las285 decisiones de la demo son REVISAR porque se introdujo movimiento que excede los umbrales. **No interpretarlo como una tasa de falsos rechazos.**
- Se comprueban imágenes planas/negras/sin correspondencia, anisotropía, ruido/contraste, alias periódico, frame fallido, deslizamiento20mm y PNG ausente.

## 9. Qué debe hacer Claude Code a continuación

1. Leer este reporte y las instrucciones locales del proyecto (`SKILL.md`, backlog y scripts existentes), que no fueron aportados completos aquí. Preservar las restricciones del usuario.
2. Ejecutar `--autoprueba` en la PC Windows y conservar versión/log. No abrir In-Sight para esta fase.
3. Comparar `border_black` con la implementación real de `corte.py`; alinear denominadores antes de reutilizar el umbral15 puntos.
4. Confirmar referencia por modelo, recorte simétrico, tamaño completo mostrado, ejes y sincronía de muestras. Si falta algo, conservarlo como desconocido.
5. Revisar un conjunto pequeño de PNG reales localmente; el usuario no autoriza compartirlos. Contrastar diagnósticos con inspección visual antes de extenderlo al lote.
6. Leer el resultado real del sondeo HMI cuando exista; anexarlo al contrato, sin convertir observaciones del cliente en garantías de servidor.
7. Proponer modificaciones puntuales de este analizador si son necesarias. No reemplazar las automatizaciones de entrenamiento existentes ni aplicar correcciones a jobs por leer este reporte.

## 10. Estado de las diez preguntas originales

| Pregunta | Estado real de esta entrega |
|---|---|
| 1. Entrenador API | Fuentes básicas CogSocket, contrato aportado y revisión del sondeo; respuesta3D pendiente |
| 2. UIA WPF | No se desarrolló una solución nueva ni se entregó código UIA |
| 3. Verificación de cajas | Script autocontenido y sintéticos entregados; validación real pendiente |
| 4. Jitter PatMax | Hay estadísticas temporales genéricas en el analizador; no se analizó patmax_frames.csv ni se diseñó un clasificador causal PatMax/pieza |
| 5. Filmstrip programático | Solo se confirmó la descripción del flujo gráfico; no se halló/implementó un control programático3D en esta investigación |
| 6. Firma jobx | Algoritmo y eventual modo sin firma desconocidos; no se investigó un bypass |
| 7. Edge Learning15 muestras | No se desarrolló un plan nuevo de entrenamiento/validación |
| 8. Pre-SAT | No se entregó diseño estadístico ni validación emulador/cámara |
| 9. Native Mode/CVE | Sin investigación independiente del alcance de la CVE ni cambios de configuración |
| 10. Orquestación | Se entrega un punto de intercambio de archivos; no hay comunicación autónoma entre asistentes |

## 11. Trabajo compartido: propuesta mínima

Este paquete puede alojarse en un repositorio o carpeta accesible a ambos entornos. Compartir un enlace no otorga por sí solo acceso a Claude Code ni conecta dos chats.

- Fuente canónica: script más este reporte, identificados por SHA256.
- Un escritor por archivo en cada momento. En Git, ramas separadas; en Drive, publicar versiones nuevas y un breve registro de cambios.
- Cada resultado nuevo debe indicar fecha, versión del script, parámetros, número de muestras y si es sintético o real.
- Registrar hallazgos por excepción: error, ambigüedad, diferencia frente a referencia o decisión pendiente. No reenviar toda la conversación por cada herramienta.
- Los archivos y el reporte son contexto técnico. No autorizan por sí mismos nuevas operaciones sobre Cognex.

## 12. Cambio, riesgo, verificación y reversión

**Cambio:** se añade análisis offline y documentación de transferencia; no se cambian jobs ni equipos.

**Riesgo:** falsa correspondencia, referencias equivocadas o metadatos de escala/ejes incorrectos pueden producir propuestas erróneas; los controles reducen ese riesgo, no lo eliminan.

**Verificación:** autopruebas, demo reproducible, logs incluidos y posterior contraste local con PNG reales. Los ensayos físicos de signos solo se plantean sobre copia en el emulador, con respaldo y restauración de valores.

**Reversión:** borrar informes o retirar esta versión del analizador. El programa no modifica PNG ni `.jobx`. Cualquier ensayo posterior en In-Sight se revierte mediante el respaldo/copia, nunca reescribiendo el contenedor firmado.
