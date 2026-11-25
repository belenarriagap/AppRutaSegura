# AppRutaSegura

Simulación **offline** de evacuación ante sismos a partir del plano 2D de un local.

## Descarga y prueba

El instalador/ejecutable para Windows (`.zip` con el `.exe`) y un archivo **DWG de ejemplo** para hacer la prueba están disponibles en Google Drive:

👉 **[Descargar AppRutaSegura (.exe) y plano DWG de prueba](https://drive.google.com/drive/folders/1lzvJG-zXGerwXgcw9IIsDrqto8bnbaWK?usp=sharing)**

### Pasos

1. Descarga el `.zip` desde el enlace de Drive y descomprímelo.
2. Ejecuta el `.exe` de AppRutaSegura.
3. Carga el archivo `.dwg` de prueba incluido en la misma carpeta de Drive.
4. Ejecuta la simulación de evacuación y revisa las rutas generadas.

## Estructura del repositorio

| Carpeta | Contenido |
|---|---|
| `abp_rutasegura/` | Código fuente de la aplicación (dominio, aplicación, datos, motores, presentación y recursos) |
| `abp_packaging/` | Lanzador, spec de PyInstaller e instalador de Windows (Inno Setup) |
| `abp_scripts/` | Scripts de compilación para Windows y evaluación de visión |
| `abp_tests/` | Pruebas unitarias, de integración, de arquitectura y benchmarks |

## Ejecutar desde el código fuente

Requiere **Python 3.12**.

```bash
pip install -e .
abp-rutasegura
```

Para ejecutar las pruebas:

```bash
pytest
```
