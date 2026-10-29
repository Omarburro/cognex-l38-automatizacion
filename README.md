# Cognex L38: análisis offline y entrega a Claude Code

Proyecto: **Inspection T1XX**.

Código y resultados **sintéticos** para verificar miniaturas Edge AI 3D. El analizador no se conecta a Cognex ni modifica jobs.

1. Leer [el reporte completo](LEEME_PARA_CLAUDE.md).
2. Copiar [el mensaje de transferencia](MENSAJE_PARA_CLAUDE.txt) a Claude Code.
3. Revisar [el contrato HMI observado](CONTRATO_HMI_OBSERVADO.md): soporte del entrenador3D pendiente de prueba.
4. Ejecutar [revisar_cajas.py](revisar_cajas.py) con `--autoprueba` antes de usar imágenes locales.

```powershell
python -m pip install -r .\requirements.txt
python .\revisar_cajas.py --autoprueba
python .\revisar_cajas.py --guia
```

Resultados de esta entrega: [resumen verificable](resultados_verificados/resumen_verificacion.json), [autopruebas](resultados_verificados/autoprueba.txt) y [demo](demo_sintetica/).

**Verificado en documentación Cognex:** fuentes y alcance en el reporte; no equivalen a probar el servidor instalado.

**Probado aquí:** sintéticos con Python/OpenCV. **Por probar:** Windows, miniaturas reales, metadatos físicos y respuesta del entrenador3D.

Restricciones: solo emulador sobre copia respaldada; nunca cámaras/PLC ni edición externa de `.jobx`; nunca cambios de tamaño/fixture. Las propuestas no se aplican automáticamente. Z no identificable con estos PNG.

Para colaborar, ambos asistentes necesitan acceso al mismo repositorio. Un enlace no conecta automáticamente sus sesiones. Usar ramas distintas y registrar cambios y pruebas.
