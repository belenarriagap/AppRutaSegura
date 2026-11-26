from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class abpProjectTexts:
    abp_menu_new: str = "&Nuevo proyecto…"
    abp_menu_open: str = "&Abrir proyecto…"
    abp_menu_save: str = "&Guardar"
    abp_new_title: str = "Nuevo proyecto"
    abp_open_title: str = "Abrir proyecto"
    abp_name: str = "Nombre del local:"
    abp_use: str = "Tipo de local:"
    abp_address: str = "Dirección (opcional):"
    abp_use_labels: tuple[tuple[str, str], ...] = (
        ("educacion", "Educación (colegio, instituto)"),
        ("oficinas", "Oficinas"),
        ("comercio", "Comercio (tienda, restaurante)"),
    )
    abp_name_required: str = "Escriba el nombre del local."
    abp_no_projects: str = "Todavía no hay proyectos. Cree uno nuevo."
    abp_saved: str = "Cambios guardados."
    abp_opened: str = "Proyecto abierto: {name}"
    abp_welcome_new: str = "Crear un proyecto nuevo"
    abp_welcome_open: str = "Abrir otro proyecto…"
    abp_recent_title: str = "Sus proyectos"
    abp_recent_empty: str = "Todavía no hay proyectos. Empiece creando uno nuevo."
    abp_recent_item: str = "{name}\n{use} · creado el {date}"
    abp_recent_hint: str = "Doble clic para abrir. Clic derecho: duplicar, exportar o eliminar."
    abp_menu_import: str = "&Importar proyecto…"
    abp_menu_export: str = "&Exportar proyecto…"
    abp_menu_duplicate: str = "&Duplicar proyecto"
    abp_menu_delete: str = "E&liminar proyecto…"
    abp_welcome_import: str = "Importar…"
    abp_item_open: str = "Abrir"
    abp_archive_filter: str = "Proyecto de RutaSegura (*.rutasegura)"
    abp_export_title: str = "Exportar proyecto"
    abp_import_title: str = "Importar proyecto"
    abp_exported: str = "Proyecto exportado en: {path}"
    abp_imported: str = "Proyecto importado: {name}"
    abp_duplicated: str = "Se creó la copia «{name}»."
    abp_confirm_delete: str = (
        "¿Eliminar el proyecto «{name}» con sus pisos, escenarios y simulaciones? "
        "Esta acción no se puede deshacer. Si quiere conservar una copia, expórtelo antes."
    )
    abp_deleted: str = "Se eliminó el proyecto «{name}»."
    abp_error_title: str = "No se pudo completar la acción"
    abp_menu_details: str = "&Datos del local…"
    abp_details_button: str = "Datos del local"
    abp_details_title: str = "Datos del local"
    abp_details_help: str = (
        "Estos datos aparecen en la portada del informe y en el mapa de evacuación. Solo el "
        "nombre es obligatorio."
    )
    abp_section_general: str = "Local"
    abp_section_location: str = "Ubicación"
    abp_section_contact: str = "Responsable y contacto"
    abp_section_other: str = "Otros"
    abp_district: str = "Distrito:"
    abp_province: str = "Provincia:"
    abp_department: str = "Departamento:"
    abp_responsible: str = "Responsable:"
    abp_responsible_placeholder: str = "Director(a), administrador(a) o jefe(a) de brigada"
    abp_responsible_role: str = "Cargo:"
    abp_phone: str = "Teléfono:"
    abp_email: str = "Correo:"
    abp_schedule: str = "Horario de mayor concurrencia:"
    abp_schedule_placeholder: str = "Por ejemplo: lunes a viernes de 8:00 a 13:00"
    abp_notes: str = "Observaciones:"
    abp_logo: str = "Logo:"
    abp_logo_choose: str = "Elegir imagen…"
    abp_logo_remove: str = "Quitar"
    abp_logo_none: str = "Sin logo"
    abp_logo_filter: str = "Imágenes (*.png *.jpg *.jpeg)"
    abp_logo_invalid: str = "El archivo elegido no es una imagen PNG o JPG válida."
    abp_details_saved: str = "Datos del local guardados."


@dataclass(frozen=True, slots=True)
class abpWizardTexts:
    abp_load_title: str = "Paso 1. Cargar plano"
    abp_load_help: str = (
        "Elija una foto (JPG, PNG) o un PDF del plano de su local, o arrástrelo hasta aquí. Si la "
        "foto está torcida, puede enderezarla marcando las 4 esquinas del plano."
    )
    abp_choose_file: str = "Elegir foto o PDF…"
    abp_file_dialog_title: str = "Elegir plano"
    abp_file_filter: str = "Planos ({patterns})"
    abp_no_file: str = "Todavía no eligió un plano."
    abp_page_label: str = "Página del PDF:"
    abp_straighten: str = "Enderezar foto"
    abp_straighten_help: str = (
        "Haga clic en las 4 esquinas del plano, en cualquier orden. Marcadas: {count} de 4."
    )
    abp_straighten_undo: str = "Quitar enderezado"
    abp_next: str = "Siguiente"
    abp_scale_title: str = "Paso 2. Escala"
    abp_scale_help: str = (
        "Dibuje una línea sobre una medida que conozca (por ejemplo, una cota del plano o el "
        "ancho de una puerta) y escriba cuántos metros mide."
    )
    abp_scale_meters: str = "La línea mide (metros):"
    abp_scale_apply: str = "Aplicar escala"
    abp_scale_draw_first: str = "Primero dibuje la línea sobre el plano."
    abp_scale_result: str = "Escala definida: 1 metro = {px_per_m:.1f} píxeles."
    abp_scale_missing: str = (
        "Todavía no hay escala. Sin escala no se pueden calcular metros, aforo ni anchos."
    )
    abp_editor_title: str = "Paso 3. Corregir plano"
    abp_editor_help: str = (
        "Revise lo que encontró el sistema y corrija lo necesario. Las salidas en línea "
        "discontinua son propuestas: haga doble clic sobre ellas para confirmarlas. Clic derecho "
        "sobre un elemento para más opciones. En edificios de varios pisos, dibuje cada escalera "
        "en todos los pisos que une."
    )
    abp_detect: str = "Detectar automáticamente"
    abp_allow_diagonal: str = "Permitir muros en diagonal"
    abp_allow_diagonal_tip: str = (
        "Márquelo solo si el local tiene muros en diagonal. Si no, las líneas diagonales se "
        "ignoran porque suelen ser mesas o muebles."
    )
    abp_detecting: str = "Buscando muros y puertas… esto puede tardar unos segundos."
    abp_detect_done: str = (
        "Se encontraron {walls} muros, {doors} puertas, {exits} salidas, {stairs} escaleras y "
        "{obstacles} obstáculos propuestos. Use «Revisar una por una» para confirmarlos."
    )
    abp_no_image: str = "Primero cargue un plano en el paso 1."
    abp_step_not_ready: str = "Este paso todavía no está disponible."


@dataclass(frozen=True, slots=True)
class abpPdfTexts:
    abp_title: str = "Importar PDF: {name}"
    abp_help: str = (
        "Elija la lámina de su local. RutaSegura lee los trazos del PDF, así que los muros y las "
        "puertas salen con su medida exacta. Arrastre las esquinas para dejar solo el dibujo."
    )
    abp_page: str = "Lámina {number}"
    abp_level: str = "Piso {number}"
    abp_scale: str = "Escala 1/{n}"
    abp_scanned: str = "Imagen escaneada"
    abp_clean: str = "Quitar señales, flechas y colores"
    abp_clean_tip: str = (
        "Útil si la lámina ya es un mapa de evacuación o de riesgos: deja solo la arquitectura."
    )
    abp_crop: str = "Recortar al dibujo"
    abp_crop_tip: str = "Deja fuera el membrete, la leyenda y el marco de la lámina."
    abp_crop_auto: str = "Recorte sugerido"
    abp_layers: str = "Capas del plano"
    abp_layers_help: str = "Desmarque lo que no sea arquitectura (cotas, ejes, muebles, señales)."
    abp_layers_tip: str = "Las capas desmarcadas no se ven ni se usan para detectar muros."
    abp_no_layer: str = "(sin capa)"
    abp_loading: str = "Leyendo la lámina…"
    abp_accept: str = "Usar esta lámina"
    abp_cancel: str = "Cancelar"
    abp_options: str = "Lámina, capas y recorte…"
    abp_info_vector: str = "Plano vectorial: se leerán los trazos exactos."
    abp_info_scanned: str = "Lámina escaneada: se analizará como una foto."
    abp_info_scale: str = "Escala 1/{n}: se aplicará sola (podrá comprobarla en el paso 2)."
    abp_info_no_scale: str = "La lámina no dice su escala: la marcará en el paso 2."
    abp_info_rooms: str = "Ambientes rotulados ({count}): {names}."
    abp_rotate_left: str = "Girar a la izquierda"
    abp_rotate_right: str = "Girar a la derecha"
    abp_rotate_tip: str = "Gira el plano 90° (por si la lámina está de costado)."
    abp_cad_reading: str = "Leyendo el plano de AutoCAD…"
    abp_cad_help: str = "Elija las láminas que quiere abrir:"
    abp_cad_title: str = "Láminas del plano de AutoCAD"
    abp_cad_all: str = "Marcar todas"
    abp_cad_wait: str = "Puede tardar alrededor de un minuto si el dibujo es grande."
    abp_scale_fixed: str = (
        "La lámina dice 1/{written}, pero las áreas escritas indican 1/{real}: se usa esta última."
    )
    abp_info_signs: str = "Señales reconocidas ({count}): {kinds}."
    abp_signs_found: str = (
        "Se reconocieron {count} señales que ya estaban en el plano. Revíselas en el paso 3."
    )
    abp_info_kind: str = "Parece un mapa de evacuación o de riesgos: se quitan sus señales."
    abp_scale_from_sheet: str = (
        "Escala 1/{n} tomada de la lámina. Para comprobarla, dibuje una línea sobre una medida "
        "conocida."
    )
    abp_scale_check: str = "La línea que dibujó mide {meters:.2f} m con la escala actual."
    abp_plan_occupants: str = "Ocupantes según el plano"
    abp_plan_occupants_tip: str = "Usa el «AFORO=» escrito en el plano como cantidad de ocupantes."
    abp_plan_occupants_done: str = (
        "Se asignaron {count} personas según el aforo escrito en el plano."
    )
    abp_plan_occupants_none: str = "El plano no tiene aforos escritos dentro de los ambientes."


@dataclass(frozen=True, slots=True)
class abpSheetTexts:
    abp_title: str = "Lámina técnica de evacuación (formato ITSE)"
    abp_help: str = (
        "Plano a escala exacta con membrete, leyenda de señales, rutas con flechas, aforo, "
        "recorrido y tiempo de salida de cada ambiente. Una página por piso."
    )
    abp_generate: str = "Generar lámina técnica…"
    abp_default_name: str = "Lámina de evacuación - {name}"
    abp_saved: str = "Lámina guardada en: {path}"
    abp_section_sheet: str = "Lámina"
    abp_section_block: str = "Membrete"
    abp_section_times: str = "Tiempos"
    abp_paper: str = "Tamaño de papel:"
    abp_scale: str = "Escala:"
    abp_scale_auto: str = "Automática (la mayor que entre)"
    abp_underlay: str = "Fondo:"
    abp_underlay_original: str = "Plano original atenuado"
    abp_underlay_clean: str = "Plano redibujado en limpio"
    abp_furniture: str = "Trazar las rutas por los pasillos entre muebles (planos en PDF)"
    abp_signs: str = "Agregar señales propuestas (salida, flechas y aforo)"
    abp_plan_title: str = "Título del plano:"
    abp_default_title: str = "MAPA DE EVACUACIÓN Y SEÑALIZACIÓN"
    abp_code: str = "Código de lámina:"
    abp_specialist: str = "Especialista:"
    abp_drafter: str = "Dibujo:"
    abp_sector: str = "Sector:"
    abp_north: str = "Norte (giro desde arriba):"
    abp_people: str = "Personas por ambiente:"
    abp_people_capacity: str = "Aforo calculado según la norma"
    abp_people_occupants: str = "Ocupantes del paso 4"
    abp_flow: str = "Flujo en puertas K (pers/(m·s)):"
    abp_speed: str = "Velocidad V (m/s):"
    abp_formula: str = (
        "T = N / (A·K) + D / V. Los valores 1.3 y 0.6 reproducen los tiempos del plano de "
        "referencia; verifíquelos con su especialista antes de presentar la lámina."
    )
    abp_note: str = "Nota:"
    abp_default_note: str = (
        "Verificar tamaño y ubicación de las señales según la NTP 399.010-1 vigente. Este plano "
        "es de apoyo y no reemplaza la ITSE ni el estudio de un profesional colegiado."
    )
    abp_meeting_tip: str = (
        "Para que la ruta llegue al punto de reunión, dibuje una «Zona segura» fuera del edificio "
        "(paso 3)."
    )
    abp_orientation: str = "Orientación de la hoja:"
    abp_orientation_auto: str = "Automática (donde el plano salga más grande)"
    abp_orientation_landscape: str = "Horizontal"
    abp_orientation_portrait: str = "Vertical"
    abp_tables: str = "Leyenda y cuadros:"
    abp_tables_auto: str = "Automático"
    abp_tables_side: str = "Al costado del plano"
    abp_tables_bottom: str = "Debajo del plano"
    abp_identify: str = "Identificar las rutas:"
    abp_identify_room: str = "Una por ambiente (R1, R2, R3…)"
    abp_identify_exit: str = "Una por salida"
    abp_section_exits: str = "Salida de cada ambiente"
    abp_exits_help: str = (
        "El programa elige la salida más cómoda. Cámbiela si quiere repartir a las personas o "
        "seguir el criterio del especialista."
    )
    abp_exit_auto: str = "Automática"
    abp_exits_room: str = "Ambiente"
    abp_exits_exit: str = "Salida"


@dataclass(frozen=True, slots=True)
class abpStairsTexts:
    abp_button: str = "Escaleras…"
    abp_tip: str = "Indica a dónde lleva cada escalera y por qué lado se entra."
    abp_title: str = "Escaleras de este piso"
    abp_help: str = (
        "Al evacuar siempre se baja: nadie cruza una escalera que sube a otro piso. Indique a "
        "dónde lleva cada una; con «Automático» el programa lo deduce. La última columna dice "
        "qué pasará en la simulación. Al elegir una fila, la escalera se resalta en el plano."
    )
    abp_columns: tuple[str, ...] = (
        "Escalera",
        "A dónde lleva",
        "Se entra por",
        "Baja a (piso de abajo)",
        "En la simulación",
    )
    abp_side_auto: str = "Automático"
    abp_sides: tuple[str, ...] = ("la izquierda", "la derecha", "arriba", "abajo")
    abp_below_same: str = "La del mismo nombre"
    abp_roles: tuple[tuple[str, str], ...] = (
        ("paso", "Se cruza caminando (más despacio)"),
        ("baja", "Por aquí se baja al piso de abajo"),
        ("exterior", "Es una salida: lleva afuera"),
        ("cerrada", "Nadie la cruza"),
        ("pendiente", "Propuesta: confírmela para que cuente"),
    )
    abp_analyze: str = "Analizar escaleras"
    abp_analyze_tip: str = (
        "Vuelve a estudiar los peldaños, su numeración y los niveles (NPT): separa los tramos y "
        "propone a dónde lleva cada uno. No cambia las que ya tienen destino."
    )
    abp_analyze_no_lines: str = (
        "Solo para planos de PDF o AutoCAD, que traen los trazos. Indique el destino a mano."
    )
    abp_analyzed: str = "Escaleras analizadas: {count}. Revise a dónde lleva cada una."
    abp_analyzed_same: str = "El análisis no encontró nada nuevo en las escaleras."
    abp_confirm: str = "Confirmar todas"
    abp_close: str = "Listo"
    abp_cmd: str = "cambiar escalera"
    abp_empty: str = (
        "Este piso no tiene escaleras. Dibújelas con la herramienta «Escalera» o use «Analizar "
        "escaleras»."
    )


@dataclass(frozen=True, slots=True)
class abpRouteTexts:
    abp_button: str = "Editar rutas"
    abp_tip: str = "Corrige a mano por dónde sale cada ambiente."
    abp_title: str = "Rutas de salida"
    abp_help: str = (
        "Arrastre una ruta para desviarla: se agrega un punto por donde debe pasar. Mueva los "
        "puntos con el mouse y quítelos con clic derecho. Para cambiar de salida, elíjala en la "
        "lista o arrastre el cuadrado del final hasta ella. Doble clic en un ambiente elige su "
        "ruta."
    )
    abp_columns: tuple[str, ...] = ("Parte de", "Sale por", "Ruta")
    abp_room: str = "{name} ({people} pers.)"
    abp_from_stair: str = "Quienes bajan por {name}"
    abp_automatic: str = "Automática"
    abp_automatic_to: str = "Automática ({name})"
    abp_closed: str = "{name} (bloqueada)"
    abp_state_auto: str = "Automática"
    abp_state_manual: str = "A mano"
    abp_undo: str = "Deshacer"
    abp_reset: str = "Volver a la automática"
    abp_reset_all: str = "Todas automáticas"
    abp_done: str = "Listo"
    abp_remove_point: str = "Quitar este punto"
    abp_point_tip: str = "Arrastre para mover; clic derecho para quitar"
    abp_end_tip: str = "Arrastre hasta otra salida"
    abp_no_exit_there: str = "Suelte el final de la ruta sobre una salida de la lista."
    abp_pending: str = "Las rutas cambiaron: pulse «Simular» para ver el nuevo resultado."


@dataclass(frozen=True, slots=True)
class abpElementsTexts:
    abp_button: str = "Elementos del plano"
    abp_tip: str = (
        "Lista de todo lo reconocido: puertas y ventanas con su rótulo, muebles, señales…"
    )
    abp_title: str = "Elementos del plano"
    abp_help: str = (
        "Todo lo que el programa reconoce en este piso. Elija un elemento para verlo en el plano."
    )
    abp_search: str = "Buscar (por ejemplo: extintor, P-01, ventana)…"
    abp_column_element: str = "Elemento"
    abp_column_detail: str = "Detalle"
    abp_kinds: tuple[tuple[str, str], ...] = (
        ("salida", "Salidas"),
        ("puerta", "Puertas"),
        ("escalera", "Escaleras"),
        ("ambiente", "Ambientes"),
        ("senal", "Señales"),
        ("zona_segura", "Zonas seguras y de reunión"),
        ("obstaculo", "Muebles y obstáculos"),
        ("silla", "Sillas (no bloquean el paso)"),
        ("columna", "Columnas"),
        ("ventana", "Ventanas"),
        ("muro", "Muros"),
    )


@dataclass(frozen=True, slots=True)
class abpEditorTexts:
    abp_tool_select: str = "Seleccionar"
    abp_tool_wall: str = "Muro"
    abp_tool_door: str = "Puerta"
    abp_tool_exit: str = "Salida"
    abp_tool_stair: str = "Escalera"
    abp_tool_obstacle: str = "Obstáculo"
    abp_tool_safe_zone: str = "Zona segura"
    abp_tool_sign: str = "Señal"
    abp_delete: str = "Borrar"
    abp_confirm_exit: str = "Confirmar salida"
    abp_confirm_all: str = "Confirmar todas"
    abp_undo: str = "Deshacer"
    abp_redo: str = "Rehacer"
    abp_fit: str = "Ver todo"
    abp_layers: str = "Capas visibles"
    abp_layer_background: str = "Plano de fondo"
    abp_layer_walls: str = "Muros"
    abp_layer_doors: str = "Puertas"
    abp_layer_exits: str = "Salidas"
    abp_layer_stairs: str = "Escaleras"
    abp_layer_obstacles: str = "Obstáculos"
    abp_layer_safe_zones: str = "Zonas seguras"
    abp_layer_signs: str = "Señales"
    abp_hint_select: str = (
        "Clic: seleccionar. Arrastre un nodo (cuadradito) para mover una esquina. Doble clic en "
        "una salida propuesta: confirmarla. Clic derecho: más opciones. Supr: borrar."
    )
    abp_hint_segment: str = "Arrastre para dibujar. Mantenga Mayús para líneas rectas."
    abp_hint_area: str = "Arrastre para dibujar un rectángulo."
    abp_hint_zoom: str = "Rueda del mouse: acercar o alejar. Botón central: desplazar."
    abp_tip_select: str = "Seleccionar elementos. Clic derecho sobre uno para más opciones."
    abp_tip_wall: str = "Dibujar un muro: arrastre de un extremo al otro."
    abp_tip_door: str = "Marcar una puerta: arrastre sobre el muro; se encaja sola y abre el hueco."
    abp_tip_exit: str = "Marcar una salida al exterior: arrastre sobre un muro exterior."
    abp_tip_stair: str = "Marcar una escalera: arrastre un rectángulo."
    abp_tip_obstacle: str = "Marcar un mueble u obstáculo que no se puede atravesar."
    abp_tip_sign: str = "Colocar una señal de seguridad (salida, extintor, botiquín…)."
    abp_sign_combo_tip: str = "Señal que se colocará al hacer clic en el plano."
    abp_hint_sign: str = (
        "Elija la señal en la lista y haga clic donde va. Con la herramienta Seleccionar puede "
        "arrastrarla, girarla o borrarla."
    )
    abp_tool_identify: str = "Identificar"
    abp_tip_identify: str = (
        "Haga clic sobre algo del dibujo y el programa reconoce su forma: mesa, escalera, hueco…"
    )
    abp_identify_combo_tip: str = "Qué es lo que va a señalar en el plano."
    abp_hint_identify: str = (
        "Elija en la lista qué va a señalar y haga clic encima, tantas veces como quiera. Para "
        "puertas y salidas, haga clic en el hueco. Si ya era otra cosa, se convierte."
    )
    abp_identify_no_scale: str = (
        "Primero defina la escala (paso 2): hace falta para reconocer formas."
    )
    abp_identify_nothing: str = (
        "Ahí no se reconoce nada como {kind}. Pruebe más al centro o dibújelo."
    )
    abp_identify_done: str = "Marcado como {kind}."
    abp_cmd_identify: str = "identificar {kind}"
    abp_cmd_convert: str = "convertir en {kind}"
    abp_menu_confirm_other: str = "Confirmar"
    abp_menu_convert: str = "Convertir en {kind}"
    abp_confirm_exits: str = "Confirmar salidas"
    abp_confirm_stairs: str = "Confirmar escaleras"
    abp_confirm_obstacles: str = "Confirmar obstáculos"
    abp_confirm_everything: str = "Confirmar todo"
    abp_pending_others: str = (
        "Hay {count} escaleras u obstáculos propuestos: no cuentan hasta que los confirme."
    )
    abp_review_start: str = "Revisar una por una"
    abp_review_tip: str = (
        "Recorre las salidas, escaleras, puertas dudosas y obstáculos propuestos: usted solo dice "
        "sí o no."
    )
    abp_review_question: str = "¿Esto es {article} {kind}?"
    abp_review_masculine: str = "un"
    abp_review_feminine: str = "una"
    abp_review_yes: str = "Sí"
    abp_review_no: str = "No, quitar"
    abp_review_no_wall: str = "No, es muro"
    abp_review_all: str = "Sí a todos"
    abp_review_other: str = "Es {kind}"
    abp_review_skip: str = "Después"
    abp_review_close: str = "Terminar"
    abp_review_finished: str = "Revisión terminada: respondió {count} preguntas."
    abp_prop_rotation: str = "Giro"
    abp_prop_sign_text: str = "Texto"
    abp_cmd_sign: str = "cambiar señal"
    abp_propose_signs: str = "Proponer señales"
    abp_menu_stair_use: str = "Destino de la escalera"
    abp_stair_uses: tuple[tuple[str, str], ...] = (
        ("automatico", "Automático"),
        ("sube", "Sube al piso de arriba"),
        ("baja", "Baja al piso de abajo"),
        ("sube_baja", "Sube y baja"),
        ("mismo_piso", "Gradas de este mismo piso (se cruzan)"),
        ("exterior", "Sale directamente al exterior"),
        ("no_se_usa", "No se usa al evacuar"),
    )
    abp_stair_marks: tuple[tuple[str, str], ...] = (
        ("sube", "↑ sube"),
        ("baja", "↓ baja"),
        ("sube_baja", "↕ sube y baja"),
        ("mismo_piso", "gradas"),
        ("exterior", "→ exterior"),
        ("no_se_usa", "✕ no se usa"),
    )
    abp_rotate_plan: str = "Girar plano 90°"
    abp_rotate_plan_tip: str = (
        "Pasa el plano de horizontal a vertical (o al revés) con todo lo dibujado."
    )
    abp_propose_signs_tip: str = (
        "Coloca SALIDA sobre cada salida, flechas donde la ruta dobla y el aforo en cada puerta. "
        "Extintores, botiquín, luces y zonas seguras los coloca usted."
    )
    abp_propose_signs_done: str = "Se agregaron {count} señales propuestas. Revíselas y muévalas."
    abp_propose_signs_none: str = (
        "No hay señales nuevas que proponer (¿faltan salidas confirmadas o ambientes?)."
    )
    abp_tip_safe_zone: str = "Marcar una zona segura (patio, explanada) a la que se puede evacuar."
    abp_tip_shortcut: str = "{tip}\nAtajo: {key}"
    abp_legend_title: str = "Leyenda y capas"
    abp_legend_dashed: str = "Línea discontinua: salida propuesta, falta confirmarla."
    abp_legend_low: str = "Naranja: detectado con poca seguridad; revíselo."
    abp_menu_confirm: str = "Confirmar salida"
    abp_menu_rename: str = "Cambiar nombre…"
    abp_menu_delete: str = "Borrar"
    abp_rename_title: str = "Cambiar nombre"
    abp_rename_label: str = "Nombre:"
    abp_name_empty: str = "Escriba un nombre."
    abp_name_in_use: str = "Ya existe otro elemento llamado «{name}» en este piso."
    abp_cmd_rename: str = "Cambiar nombre a «{name}»"
    abp_snap: str = "Imán"
    abp_snap_tip: str = "Pega el cursor a nodos, cruces y puntos sobre los muros.\nAtajo: F3"
    abp_ortho: str = "Ortogonal"
    abp_ortho_tip: str = "Dibuja solo líneas horizontales o verticales.\nAtajo: F8"
    abp_show_nodes: str = "Nodos"
    abp_show_nodes_tip: str = (
        "Muestra los nodos (esquinas y extremos). Arrástrelos con la herramienta Seleccionar: "
        "todo lo que termina en un nodo se mueve con él."
    )
    abp_clean: str = "Limpiar plano"
    abp_clean_tip: str = (
        "Une muros duplicados y cierra esquinas o uniones que quedaron abiertas por pocos "
        "centímetros. Los huecos anchos (posibles puertas) no se tocan."
    )
    abp_clean_done: str = (
        "Plano limpio: se unieron {merged} muro(s) duplicado(s), se cerraron {joined} unión(es) "
        "abierta(s) y se quitaron {removed} muro(s) diminuto(s). Puede deshacerlo con Ctrl+Z."
    )
    abp_clean_nothing: str = (
        "El plano ya estaba limpio: no hay muros duplicados ni uniones abiertas."
    )
    abp_cmd_move_node: str = "Mover nodo"
    abp_cmd_length: str = "Cambiar longitud"
    abp_cmd_clean: str = "Limpiar plano"
    abp_properties: str = "Propiedades"
    abp_prop_kind: str = "Elemento:"
    abp_prop_length: str = "Longitud:"
    abp_prop_name: str = "Nombre:"
    abp_prop_hint: str = (
        "Escriba la medida exacta: el extremo final se mueve y arrastra lo que esté unido."
    )
    abp_kind_names: tuple[tuple[str, str], ...] = (
        ("muro", "Muro"),
        ("puerta", "Puerta"),
        ("salida", "Salida"),
        ("escalera", "Escalera"),
        ("obstaculo", "Obstáculo"),
        ("zona_segura", "Zona segura"),
        ("senal", "Señal"),
    )
    abp_pending_exits: str = "Hay {count} salida(s) propuesta(s) por confirmar."
    abp_exit_name: str = "Salida {number}"
    abp_proposed_suffix: str = " (por confirmar)"
    abp_stair_name: str = "Escalera {letter}"
    abp_cmd_add: str = "Agregar {what}"
    abp_cmd_delete: str = "Borrar {count} elemento(s)"
    abp_cmd_confirm: str = "Confirmar {count} salida(s)"
    abp_cmd_detect: str = "Detección automática"


@dataclass(frozen=True, slots=True)
class abpRoomsTexts:
    abp_title: str = "Paso 4. Ambientes y ocupantes"
    abp_help: str = (
        "Marque cada ambiente del local e indique cuántas personas de cada tipo hay en él "
        "en el momento más concurrido. Puede detectarlos automáticamente o dibujarlos "
        "haciendo clic en sus esquinas (doble clic para terminar)."
    )
    abp_detect: str = "Detectar ambientes"
    abp_draw: str = "Dibujar ambiente"
    abp_delete: str = "Borrar ambiente"
    abp_name_template: str = "Ambiente {number}"
    abp_column_name: str = "Ambiente"
    abp_column_use: str = "Tipo de ambiente"
    abp_column_area: str = "Área (m²)"
    abp_total: str = "Total: {count} personas"
    abp_no_scale: str = "Primero defina la escala (paso 2): sin ella no se calculan las áreas."
    abp_detected: str = "Se agregaron {count} ambiente(s). Revise sus nombres."
    abp_nothing_detected: str = (
        "No se encontraron ambientes cerrados nuevos. Revise que los muros y puertas estén "
        "completos o dibújelos a mano."
    )


@dataclass(frozen=True, slots=True)
class abpSimulationTexts:
    abp_title: str = "Paso 6. Simular la evacuación"
    abp_help: str = (
        "Simula un sismo: cada persona espera su tiempo de reacción y luego camina hacia la "
        "salida más cercana. Con la misma semilla, el resultado es siempre el mismo."
    )
    abp_seed: str = "Semilla:"
    abp_run: str = "Simular"
    abp_cancel: str = "Cancelar"
    abp_running: str = "Simulando… {percent:.0f} %"
    abp_cancelled: str = "Simulación cancelada."
    abp_play: str = "Reproducir"
    abp_pause: str = "Pausa"
    abp_speed: str = "Velocidad:"
    abp_heatmap: str = "Mapa de calor"
    abp_routes: str = "Rutas"
    abp_routes_tip: str = (
        "Muestra la ruta de evacuación de cada ambiente hasta su salida (en verde la automática; "
        "en azul la corregida a mano)."
    )
    abp_time: str = "{now} / {end}"
    abp_evacuated: str = "Evacuados: {done} de {total}"
    abp_results_title: str = "Resultados"
    abp_card_total: str = "Tiempo total"
    abp_card_ninety: str = "90 % evacuado"
    abp_card_evacuated: str = "Personas evacuadas"
    abp_card_evacuated_value: str = "{done} de {total}"
    abp_note_all_out: str = "Salieron todas las personas."
    abp_note_left: str = "Quedaron {left} persona(s) dentro."
    abp_note_congestion: str = "{count} zona(s) con congestión."
    abp_note_no_congestion: str = "Sin congestión sostenida."
    abp_note_ninety: str = "Momento en que salió el 90 % de las personas."
    abp_per_exit_title: str = "Tiempo por salida"
    abp_floors_title: str = "Desalojo por piso"
    abp_refresh: str = "Actualizar plano"
    abp_refresh_tip: str = (
        "Vuelve a cargar el plano, los ambientes y los ocupantes actuales de todos los pisos "
        "(por ejemplo, después de corregir los pasos 3 o 4)."
    )
    abp_refreshed: str = "Plano actualizado: se cargaron los cambios de todos los pisos."
    abp_outdated: str = (
        "El plano, los ocupantes o los ajustes cambiaron después de esta simulación: los "
        "resultados que se ven son de la versión anterior."
    )
    abp_resimulate: str = "Simular de nuevo"
    abp_floor_upper: str = (
        "Piso {number}: {people} persona(s); bajaron {descended} por la escalera; "
        "vacío a los {time}."
    )
    abp_floor_lower: str = (
        "Piso {number}: {people} persona(s) más las que bajaron; salieron todos a los {time}."
    )
    abp_floor_not_cleared: str = "Piso {number}: {people} persona(s); el piso no llegó a vaciarse."
    abp_viewer_floor: str = "En este piso: {here} · en la escalera: {stairs}"
    abp_runs: str = "Corridas:"
    abp_runs_tip: str = (
        "Cuántas veces se repite la simulación con semillas distintas. Con más de una se "
        "muestra el promedio y el peor caso (P95)."
    )
    abp_running_runs: str = "Simulando {runs} corridas… {percent:.0f} %"
    abp_stats_title: str = "Varias corridas ({runs})"
    abp_stats_line: str = (
        "Promedio {mean} · desviación {std} · mejor {best} · peor {worst} · P95 {p95}. "
        "El visor muestra la corrida más cercana a la mediana (semilla {seed})."
    )
    abp_stats_incomplete: str = "En {count} de {runs} corridas no salieron todas las personas."
    abp_note_p95: str = "Promedio de {runs} corridas · peor caso (P95): {p95}"
    abp_scenario_settings: str = "Ajustes: reacción × {reaction:g}, velocidad × {speed:g}"
    abp_total_time: str = "Tiempo total de evacuación: {time}"
    abp_incomplete: str = (
        "Atención: después de {time} todavía quedaban {left} personas dentro. "
        "Revise salidas y puertas."
    )
    abp_per_exit: str = "{name}: {time}"
    abp_bottlenecks_title: str = "Cuellos de botella (del más grave al menos grave)"
    abp_no_bottlenecks: str = "No se detectaron zonas de congestión sostenida."
    abp_no_run: str = "Todavía no hay resultados. Pulse «Simular»."
    abp_provisional: str = (
        "Los parámetros del modelo son provisionales hasta calibrarlos con un simulacro real."
    )
    abp_pending_exits: str = (
        "Hay {count} salida(s) propuesta(s) sin confirmar: se tratarán como cerradas. Si son "
        "salidas reales, confírmelas en el paso 3."
    )
    abp_automatic_stairs: str = (
        "{count} escalera(s) del piso de salida están en «Automático»: nadie las cruza salvo que "
        "sean el único paso. Indique a dónde llevan en el paso 3, botón «Escaleras…»."
    )


@dataclass(frozen=True, slots=True)
class abpGuideTexts:
    abp_app_subtitle: str = "Evacuación ante sismos"
    abp_previous: str = "Anterior"
    abp_next: str = "Siguiente"
    abp_step_of: str = "Paso {number} de {total}: {name}"
    abp_go_to: str = "Ir al paso {number}"
    abp_before_step: str = "Antes de este paso (paso {number}): {issue}"
    abp_missing: str = "Qué falta: {issue}"
    abp_review: str = "Para revisar: {issue}"
    abp_step_done: str = "Este paso está completo. Puede seguir con «{next}»."
    abp_step_done_last: str = "Este paso está completo."
    abp_norms_observations: str = (
        "Para revisar: hay {count} observación(es) normativa(s) abajo, cada una con su "
        "recomendación. Puede simular igual y corregir después."
    )
    abp_issues: tuple[tuple[str, str], ...] = (
        ("sin_imagen", "cargue la foto o el PDF del plano del local."),
        ("sin_escala", "defina la escala: dibuje una línea sobre una medida que conozca."),
        ("sin_muros", "dibuje los muros del plano o use «Detectar automáticamente»."),
        (
            "sin_salidas",
            "marque al menos una salida (confirmada) o una zona segura. Dibuje la salida sobre "
            "un muro exterior con la herramienta Salida.",
        ),
        (
            "salidas_por_confirmar",
            "hay salidas propuestas sin confirmar; se tratarán como cerradas. Confírmelas con "
            "doble clic o con «Confirmar todas».",
        ),
        ("sin_ambientes", "marque los ambientes del local (detectarlos o dibujarlos)."),
        ("sin_ocupantes", "indique cuántas personas hay en cada ambiente."),
        ("sin_simulacion", "pulse «Simular» para ver cómo se evacúa el local."),
        (
            "simulacion_incompleta",
            "en la última simulación no salieron todas las personas. Revise las salidas y "
            "puertas en el paso 3.",
        ),
    )

    def abp_issue_text(self, abp_code: str) -> str:
        return dict(self.abp_issues).get(abp_code, abp_code)


@dataclass(frozen=True, slots=True)
class abpFloorTexts:
    abp_label: str = "Piso:"
    abp_name: str = "Piso {number}"
    abp_add: str = "Agregar piso"
    abp_delete: str = "Eliminar este piso"
    abp_confirm_delete: str = "¿Eliminar el {name} con su plano, ambientes y ocupantes?"
    abp_max_floors: str = "RutaSegura trabaja con edificios de hasta 4 pisos."
    abp_cannot_delete: str = "Solo se puede eliminar el piso más alto, y nunca el piso 1."
    abp_added: str = (
        "Se agregó el {name}. Cargue su plano (paso 1) y dibuje la escalera en el mismo lugar "
        "que en el piso de abajo, con el mismo nombre."
    )


@dataclass(frozen=True, slots=True)
class abpScenarioTexts:
    abp_label: str = "Escenario:"
    abp_new: str = "Nuevo escenario…"
    abp_edit: str = "Editar…"
    abp_delete: str = "Eliminar"
    abp_compare: str = "Comparar escenarios…"
    abp_dialog_new_title: str = "Nuevo escenario «qué pasa si»"
    abp_dialog_edit_title: str = "Editar escenario"
    abp_name: str = "Nombre:"
    abp_occupancy: str = "Ocupación respecto del escenario base:"
    abp_occupancy_result: str = "= {count} personas (el escenario base tiene {base})."
    abp_blocked: str = "Salidas bloqueadas en este escenario:"
    abp_no_exits: str = "El plano no tiene salidas confirmadas."
    abp_base_hint: str = (
        "Las personas del escenario base se indican en el paso 4. Los demás escenarios copian "
        "esa ocupación con el porcentaje elegido."
    )
    abp_confirm_delete: str = "¿Eliminar el escenario «{name}» y sus simulaciones?"
    abp_compare_title: str = "Comparar escenarios"
    abp_compare_need_two: str = "Simule al menos dos escenarios para poder compararlos."
    abp_play_both: str = "Reproducir ambos"
    abp_metric: str = "Indicador"
    abp_difference: str = "Diferencia (B − A)"
    abp_row_people: str = "Personas"
    abp_row_blocked: str = "Salidas bloqueadas"
    abp_row_total: str = "Tiempo total de evacuación"
    abp_row_half: str = "Tiempo para evacuar al 50 %"
    abp_row_ninety: str = "Tiempo para evacuar al 90 %"
    abp_row_evacuated: str = "Evacuados"
    abp_row_bottlenecks: str = "Cuellos de botella"
    abp_row_exit: str = "Tiempo por «{name}»"
    abp_none: str = "Ninguna"
    abp_not_used: str = "sin uso"
    abp_template: str = "Plantilla:"
    abp_templates: tuple[str, ...] = (
        "Personalizado",
        "Más personas que lo habitual (150 %)",
        "Salida principal bloqueada",
        "Reacción lenta (por ejemplo, de noche): tiempo de reacción × 2",
        "Desplazamiento difícil (escombros, poca luz): velocidad × 0,7",
    )
    abp_template_hint: str = (
        "Las plantillas son ejemplos de partida: ajuste los valores a su local. No son valores "
        "normativos."
    )
    abp_description: str = "Descripción:"
    abp_description_placeholder: str = "Qué representa este escenario (opcional)"
    abp_section_people: str = "Personas"
    abp_section_blocked: str = "Salidas y zonas seguras bloqueadas"
    abp_section_behavior: str = "Comportamiento"
    abp_section_runs: str = "Precisión estadística"
    abp_reaction_factor: str = "Tiempo de reacción ×"
    abp_reaction_hint: str = "1 = como en los perfiles; 2 = reaccionan en el doble de tiempo."
    abp_speed_factor: str = "Velocidad ×"
    abp_speed_hint: str = "1 = como en los perfiles; 0,7 = caminan un 30 % más lento."
    abp_runs: str = "Corridas:"
    abp_runs_hint: str = (
        "Repite la simulación con semillas distintas y muestra el promedio y el peor caso (P95). "
        "Más corridas = resultado más confiable, pero tarda más."
    )
    abp_row_mean: str = "Tiempo total promedio"
    abp_row_p95: str = "Peor caso (P95)"
    abp_row_factors: str = "Reacción × / velocidad ×"


@dataclass(frozen=True, slots=True)
class abpCalibrationTexts:
    abp_menu_tools: str = "&Herramientas"
    abp_menu_calibrate: str = "&Calibrar con un simulacro real…"
    abp_title: str = "Calibrar con un simulacro real"
    abp_help: str = (
        "Registre los datos de un simulacro de su local. El sistema prueba distintos tiempos de "
        "reacción y velocidades hasta que la simulación se parezca a lo que ocurrió."
    )
    abp_date: str = "Fecha del simulacro:"
    abp_participants: str = "Personas que participaron:"
    abp_total_time: str = "Tiempo total (hasta que salió la última persona):"
    abp_per_exit: str = "Tiempo de la última persona por cada salida (opcional, 0 = no medido):"
    abp_minutes: str = " min"
    abp_seconds: str = " s"
    abp_run: str = "Calibrar"
    abp_missing_time: str = "Indique el tiempo total que duró el simulacro."
    abp_cancel: str = "Cancelar"
    abp_running: str = "Probando combinaciones… {percent:.0f} %"
    abp_cancelled: str = "Calibración cancelada."
    abp_result: str = (
        "Error en el tiempo total: antes {before:.0%}, después {after:.0%} (meta: menos de 20 %).\n"
        "Tiempos de reacción × {reaction:g} · Velocidades × {speed:g}\n"
        "Tiempo simulado: {simulated} · Tiempo real: {observed}"
    )
    abp_target_met: str = "Se cumple la meta de validación."
    abp_target_missed: str = (
        "No se alcanzó la meta: revise los datos del simulacro, la ocupación del paso 4 o el plano."
    )
    abp_apply: str = "Aplicar a los perfiles"
    abp_applied: str = (
        "Listo: los perfiles se ajustaron. Vuelva a simular para ver los tiempos calibrados."
    )
    abp_close: str = "Cerrar"
    abp_no_project: str = "Primero abra un proyecto con plano, escala y ocupantes."


@dataclass(frozen=True, slots=True)
class abpNormsTexts:
    abp_title: str = "Paso 5. Revisar norma"
    abp_help: str = (
        "Para cada ambiente se calcula el aforo (cuántas personas puede recibir) según su "
        "categoría, y se revisan los anchos de puertas, salidas y pasillos. Elija la categoría "
        "que mejor describa el uso de cada ambiente."
    )
    abp_column_name: str = "Ambiente"
    abp_column_category: str = "Tipo de ambiente"
    abp_column_area: str = "Área (m²)"
    abp_column_capacity: str = "Aforo"
    abp_column_occupants: str = "Ocupantes"
    abp_column_travel: str = "Recorrido máx. (m)"
    abp_column_status: str = "Estado"
    abp_status_ok: str = "Correcto"
    abp_status_exceeded: str = "Excede el aforo"
    abp_status_no_capacity: str = "Sin aforo propio"
    abp_total: str = "Aforo total: {capacity} personas · Ocupantes asignados: {occupants}"
    abp_observations_title: str = "Observaciones normativas"
    abp_no_observations: str = "No se encontraron incumplimientos con las reglas usadas."
    abp_observation: str = "{description}\n{citation}"
    abp_unverified_tag: str = " · regla no verificada"
    abp_unverified_warning: str = (
        "Atención: {count} regla(s) usada(s) todavía no fueron verificadas con el texto oficial "
        "del RNE. Los resultados son orientativos hasta confirmarlas."
    )
    abp_no_scale: str = "Primero defina la escala del plano (paso 2)."
    abp_verify_rules: str = "Verificar reglas…"
    abp_category_suggested: str = "Sugerida por el nombre del ambiente"
    abp_rules_menu: str = "&Reglas normativas…"
    abp_rules_title: str = "Reglas normativas"
    abp_rules_help: str = (
        "Cada regla trae un valor de referencia que todavía no fue contrastado con el texto "
        "oficial del RNE: por eso el informe la marca «No verificada». Si usted (o un "
        "profesional) revisó la norma oficial, ingrese el valor y el artículo y márquela como "
        "verificada. Se aplica a todos los proyectos de este equipo."
    )
    abp_rules_filter_all: str = "Todas"
    abp_rules_filter_pending: str = "Sin verificar"
    abp_rules_filter_done: str = "Verificadas"
    abp_rules_column_rule: str = "Regla"
    abp_rules_column_value: str = "Valor"
    abp_rules_column_citation: str = "Norma y artículo"
    abp_rules_column_state: str = "Estado"
    abp_rules_state_pending: str = "No verificada"
    abp_rules_state_done: str = "Verificada"
    abp_rules_state_done_by: str = "Verificada por {who} el {date}"
    abp_rules_form_title: str = "Verificar la regla seleccionada"
    abp_rules_original: str = "Valor de referencia: {value} · {citation}"
    abp_rules_value: str = "Valor oficial:"
    abp_rules_no_capacity: str = "Sin aforo propio (no suma al aforo)"
    abp_rules_norm: str = "Norma:"
    abp_rules_article: str = "Artículo:"
    abp_rules_source: str = "Documento consultado:"
    abp_rules_source_placeholder: str = (
        "Por ejemplo: RNE A.130, D.S. N.º 011-2006-VIVIENDA y modificatorias"
    )
    abp_rules_by: str = "Verificado por:"
    abp_rules_date: str = "Fecha:"
    abp_rules_confirm: str = "Confirmo que contrasté este valor con el texto oficial vigente."
    abp_rules_save: str = "Guardar verificación"
    abp_rules_reset: str = "Volver al valor de referencia"
    abp_rules_need_confirm: str = "Marque la confirmación de que revisó el texto oficial."
    abp_rules_need_name: str = "Indique quién verificó la regla."
    abp_rules_saved: str = "Regla verificada: {rule}."
    abp_rules_counter: str = "{done} de {total} reglas verificadas"


@dataclass(frozen=True, slots=True)
class abpReportTexts:
    abp_title: str = "Paso 7. Informe"
    abp_help: str = (
        "Genere un informe PDF con el tiempo estimado de evacuación, el mapa de calor, los "
        "cuellos de botella, el aforo y las observaciones normativas, para compartirlo con su "
        "comité o brigada."
    )
    abp_generate: str = "Generar informe PDF…"
    abp_generating: str = "Generando el informe…"
    abp_open: str = "Abrir informe"
    abp_save_title: str = "Guardar informe"
    abp_save_filter: str = "Documento PDF (*.pdf)"
    abp_default_name: str = "Informe de evacuación - {name}.pdf"
    abp_saved: str = "Informe guardado en:\n{path}"
    abp_no_run: str = (
        "Todavía no simuló la evacuación: el informe no incluirá tiempos ni mapa de calor. "
        "Puede simular en el paso 6."
    )
    abp_ready: str = "El informe incluirá la última simulación guardada."
    abp_map_title: str = "Mapa de evacuación"
    abp_map_help: str = (
        "Genere el plano de evacuación para imprimir y colocar en el local: rutas en verde, "
        "salidas, zonas seguras, «Usted está aquí», leyenda e indicaciones en caso de sismo."
    )
    abp_map_generate: str = "Generar mapa de evacuación…"
    abp_map_dialog_title: str = "Mapa de evacuación"
    abp_map_paper: str = "Tamaño de papel:"
    abp_map_here: str = "«Usted está aquí» en el {floor}:"
    abp_map_here_none: str = "No mostrar"
    abp_map_responsible: str = "Responsable:"
    abp_map_meeting_point: str = "Punto de reunión:"
    abp_map_meeting_placeholder: str = "Por ejemplo: losa deportiva frente al local"
    abp_map_phones: str = "Teléfonos de emergencia (verifíquelos para su localidad):"
    abp_map_phone_service: str = "Servicio"
    abp_map_phone_number: str = "Número"
    abp_map_instructions: str = "Indicaciones en caso de sismo (una por línea):"
    abp_map_default_name: str = "Plano de evacuación - {name}.pdf"
    abp_map_saved: str = "Mapa de evacuación guardado en:\n{path}"
    abp_map_generating: str = "Generando el mapa…"
    abp_map_default_phones: tuple[tuple[str, str], ...] = (
        ("Bomberos", "116"),
        ("Policía Nacional", "105"),
        ("SAMU (emergencias médicas)", "106"),
    )
    abp_map_default_instructions: tuple[str, ...] = (
        "Mantenga la calma y aléjese de ventanas, vidrios y objetos que puedan caer.",
        "Si no puede salir de inmediato, ubíquese junto a columnas o muros estructurales.",
        "Cuando el movimiento lo permita, salga por la ruta verde: no corra, no grite, no empuje.",
        "No use ascensores ni regrese por objetos personales.",
        "Ayude a niños, adultos mayores y personas con movilidad reducida.",
        "Diríjase a la zona segura o al punto de reunión y espere indicaciones de la brigada.",
    )
    abp_map_disclaimer: str = (
        "Plano de apoyo elaborado con RutaSegura. No reemplaza la señalización ni el plan de "
        "seguridad aprobados en la Inspección Técnica de Seguridad en Edificaciones (ITSE)."
    )


@dataclass(frozen=True, slots=True)
class abpUiTexts:
    abp_app_name: str
    abp_window_title: str
    abp_welcome_title: str
    abp_welcome_body: str
    abp_wizard_steps: tuple[str, ...]
    abp_menu_file: str
    abp_menu_edit: str
    abp_menu_help: str
    abp_action_quit: str
    abp_action_about: str
    abp_about_title: str
    abp_about_body: str
    abp_status_ready: str
    abp_legal_disclaimer: str
    abp_project: abpProjectTexts = field(default_factory=abpProjectTexts)
    abp_wizard: abpWizardTexts = field(default_factory=abpWizardTexts)
    abp_pdf: abpPdfTexts = field(default_factory=abpPdfTexts)
    abp_sheet: abpSheetTexts = field(default_factory=abpSheetTexts)
    abp_elements: abpElementsTexts = field(default_factory=abpElementsTexts)
    abp_stairs: abpStairsTexts = field(default_factory=abpStairsTexts)
    abp_routes: abpRouteTexts = field(default_factory=abpRouteTexts)
    abp_editor: abpEditorTexts = field(default_factory=abpEditorTexts)
    abp_rooms: abpRoomsTexts = field(default_factory=abpRoomsTexts)
    abp_simulation: abpSimulationTexts = field(default_factory=abpSimulationTexts)
    abp_norms: abpNormsTexts = field(default_factory=abpNormsTexts)
    abp_scenarios: abpScenarioTexts = field(default_factory=abpScenarioTexts)
    abp_floors: abpFloorTexts = field(default_factory=abpFloorTexts)
    abp_guide: abpGuideTexts = field(default_factory=abpGuideTexts)
    abp_calibration: abpCalibrationTexts = field(default_factory=abpCalibrationTexts)
    abp_report: abpReportTexts = field(default_factory=abpReportTexts)


abp_SPANISH = abpUiTexts(
    abp_app_name="RutaSegura",
    abp_window_title="RutaSegura — Simulación de evacuación",
    abp_welcome_title="RutaSegura",
    abp_welcome_body=(
        "Cree un proyecto nuevo o abra uno guardado. El programa revisa si las personas de su "
        "local pueden salir a tiempo durante un sismo."
    ),
    abp_wizard_steps=(
        "Cargar plano",
        "Escala",
        "Corregir plano",
        "Ambientes y ocupantes",
        "Revisar norma",
        "Simular",
        "Informe",
    ),
    abp_menu_file="&Archivo",
    abp_menu_edit="&Editar",
    abp_menu_help="A&yuda",
    abp_action_quit="&Salir",
    abp_action_about="&Acerca de RutaSegura",
    abp_about_title="Acerca de RutaSegura",
    abp_about_body=(
        "RutaSegura {version}\n\nFunciona sin internet: sus planos nunca salen de este equipo."
    ),
    abp_status_ready="Listo",
    abp_legal_disclaimer=(
        "Este informe es de apoyo y no reemplaza la Inspección Técnica de Seguridad en "
        "Edificaciones (ITSE) ni el estudio de un profesional colegiado."
    ),
)

abp_TEXTS: abpUiTexts = abp_SPANISH
