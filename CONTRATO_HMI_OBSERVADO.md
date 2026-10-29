# Contrato HMI beta: evidencia del cliente, servidor3D pendiente

Fuente aportada por el usuario: instalación26.2.1, `Runtime\webhmi\hmi-beta\chunk-BX2FP2EY.js` y `main-WLNLH57I.js`.
No se inspeccionaron los originales aquí. No se ejecutaron estas llamadas desde ChatGPT. No se recibió `beginedit_log.txt`.

## Verificado en documentación de Cognex

Existe documentación de apertura de sesión CogSocket y de setCellValue. No se encontró una especificación pública del entrenador3D en las fuentes consultadas. Fuentes y alcance en `LEEME_PARA_CLAUDE.md`.

## Observado en el cliente según fragmentos aportados

Transporte: WebSocket del emulador local, mensajes con `$type`, `id`, `path`, `body`. Los ámbitos son `root`=`cam0/hmi`, `session`=sid actual, `none`=ruta tal cual. La sesión y login deben reutilizar el cliente del equipo, no sustituirse por un ejemplo de otra versión.

`url` en esta tabla es exclusivamente la URL de edición devuelta por `beginEdit` de esa sesión/celda. Validar que resuelva al mismo emulador.

| Operación | Verbo | Ruta | Cuerpo enviado por el cliente |
|---|---|---|---|
| beginEdit | POST | sid + /beginEdit | Cadena de celda, por ejemplo `"A20"` |
| getToolEditor | GET | url + /toolEditor | Sin cuerpo |
| getClasses | GET | url + /toolEditor/classes | Sin cuerpo |
| getResult | GET | url + /toolEditor/result | Sin cuerpo |
| getConfidenceThreshold | GET | url + /toolEditor/confidenceThreshold | Sin cuerpo |
| setConfidenceThreshold | PUT | url + /toolEditor/confidenceThreshold | Entero0–100 |
| getConfidenceThresholdEditable | GET | url + /toolEditor/confidenceThresholdEditable | Sin cuerpo |
| getClassLabels | POST | url + /toolEditor/getClassLabels | Objeto vacío `{}` |
| getClassLabelImageCount | POST | url + /toolEditor/getClassLabelImageCount | Etiqueta |
| getImageIDs | POST | url + /toolEditor/getImageIDs | Etiqueta |
| getImageMetadata | GET | url + /toolEditor/image/id | Sin cuerpo |
| addCurrentImageToUnlabeled | POST | url + /toolEditor/addCurrentImageToUnlabeled | Objeto vacío `{}` |
| labelCurrentImage | POST | url + /toolEditor/labelCurrentImage | Array de una etiqueta |
| setClassLabel | POST | url + /toolEditor/setClassLabel | Array `[id_como_cadena, etiqueta]` |
| clearClassLabel | POST | url + /toolEditor/clearClassLabel | ID como cadena |
| removeImage | POST | url + /toolEditor/removeImage | ID; no afirmar tipo adicional que no conste en el fragmento |
| train | POST | url + /toolEditor/train | Objeto vacío `{}` |
| apply | POST | url + /apply | `null` |
| cancel | POST | url + /cancel | `null` |
| endEdit normal | POST | sid + /endEdit | `null` |
| setCellValue | POST | sid + /setCellValue | Array `[celda, valor]` |

`getSamples` compone `getClasses`, `getImageIDs` y consultas por ID: no implica un endpoint `/samples`.

El cliente acepta tipos `HmiELClassifyTrainer` y `HmiELReadTrainer`. Para el sondeo de clasificación solo se consultan rutas del clasificador cuando el tipo coincide exactamente con `HmiELClassifyTrainer`.

El cliente llama a `train` tras `labelCurrentImage`, `setClassLabel` y `clearClassLabel`. Eso no prueba que el servidor entrene de forma implícita al etiquetar sin la llamada posterior.

## Sondeo revisado: estado informado por el usuario

El usuario tiene `hmi_beginedit_prueba.ps1 -celda A20 -copia pruebaAPI`. Exige copia identificable, abre edición y consulta descriptor, clases, etiquetas, resultado, umbral, editabilidad, IDs, cantidades y metadatos de una muestra. Compara IDs recibidos/únicos/cantidad declarada, conserva mayúsculas exactas y repite conteos antes de cerrar. Registra respuestas y serializa con profundidad20.

- Rama entrenador reconocido: `cancel` en finally, registrando resultado. No aplica, entrena, etiqueta ni guarda.
- Rama sin entrenador: `endEdit` de edición normal, conforme al cliente observado. No afirmar inexistencia general del entrenador3D.
- Timeout de beginEdit: estado desconocido; no reintentar ni inventar URL de cancelación. No encadenar cancel/endEdit especulativos.
- No ejecutar endEdit automáticamente después de cancel.
- Una cancelación sin mutaciones no demuestra reversión de etiquetas entrenadas.
- Cerrar solamente la sesión propia por el flujo conocido; logoff no es una garantía de rollback.

## Suposición / por probar

1. Qué devuelve una celda EdgeAIClassify3D real al ejecutar beginEdit.
2. Si las consultas devuelven muestras3D de esa herramienta y cómo se identifica el grupo sin etiqueta.
3. Si addCurrentImageToUnlabeled recopila la proyección3D actual y bajo qué condiciones.
4. Si train es síncrono/asíncrono y cuál es su señal real de finalización.
5. Si cancel revierte etiquetas/modelos ya entrenados.
6. Qué confirma apply en memoria y qué requiere guardar después.

No convertir esos pendientes en APIs garantizadas. El siguiente dato necesario es el log real del sondeo, sin ejecutar escrituras adicionales por leer este documento.
