-- Esquema BASECON v2.5 para Postgres/Supabase (la app también lo crea sola al iniciar)
create schema if not exists basecon;
set search_path to basecon;

CREATE TABLE IF NOT EXISTS empresas (
        id BIGSERIAL PRIMARY KEY, rut TEXT UNIQUE NOT NULL, razon_social TEXT NOT NULL, giro TEXT,
        direccion TEXT, comuna TEXT, ciudad TEXT, telefono TEXT, email TEXT,
        region_codigo INTEGER, comuna_codigo INTEGER,
        mutual TEXT DEFAULT 'ACHS', tasa_mutual DOUBLE PRECISION DEFAULT 0.93, sucursal_mutual TEXT,
        caja_compensacion TEXT, centro_costo TEXT,
        representante_legal TEXT, rut_representante TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS trabajadores (
        id BIGSERIAL PRIMARY KEY, empresa_id INTEGER NOT NULL REFERENCES empresas(id), rut TEXT NOT NULL,
        nombres TEXT NOT NULL, apellido_paterno TEXT NOT NULL, apellido_materno TEXT,
        sexo TEXT DEFAULT 'M', fecha_nacimiento DATE, nacionalidad TEXT DEFAULT 'Chilena',
        estado_civil TEXT, direccion TEXT, comuna TEXT, email TEXT, telefono TEXT,
        afp TEXT, salud TEXT, isapre TEXT, pactado_salud_uf DOUBLE PRECISION DEFAULT 0,
        cuenta_banco TEXT, banco TEXT, tipo_cuenta TEXT DEFAULT 'RUT',
        codigo TEXT, cargo TEXT, centro_costo TEXT,
        tramo_asignacion_familiar TEXT DEFAULT 'D', numero_cargas INTEGER DEFAULT 0,
        pensionado INTEGER DEFAULT 0, cotiza_afp INTEGER DEFAULT 1,
        activo INTEGER DEFAULT 1, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(empresa_id, rut)
);

CREATE TABLE IF NOT EXISTS contratos (
        id BIGSERIAL PRIMARY KEY, trabajador_id INTEGER NOT NULL REFERENCES trabajadores(id),
        empresa_id INTEGER NOT NULL REFERENCES empresas(id), cargo TEXT NOT NULL,
        fecha_inicio DATE NOT NULL, fecha_termino DATE, tipo_contrato TEXT DEFAULT 'Indefinido',
        sueldo_base DOUBLE PRECISION NOT NULL, tipo_gratificacion TEXT DEFAULT 'Monto fijo pactado',
        gratificacion DOUBLE PRECISION DEFAULT 0, movilizacion DOUBLE PRECISION DEFAULT 0, colacion DOUBLE PRECISION DEFAULT 0,
        otros_haberes DOUBLE PRECISION DEFAULT 0, jornada_semanal INTEGER DEFAULT 42, horario TEXT,
        lugar_trabajo TEXT, observaciones TEXT, activo INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS indicadores (
        id BIGSERIAL PRIMARY KEY, periodo TEXT UNIQUE NOT NULL, uf DOUBLE PRECISION, utm DOUBLE PRECISION, tope_afp DOUBLE PRECISION,
        tope_afc DOUBLE PRECISION, tope_inp DOUBLE PRECISION, sis_tasa DOUBLE PRECISION DEFAULT 0, renta_minima DOUBLE PRECISION,
        afp_tasas TEXT, af_tramos TEXT, tasa_ccaf_salud DOUBLE PRECISION,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS factores_actualizacion (
        id BIGSERIAL PRIMARY KEY, anio_rentas INTEGER NOT NULL, mes INTEGER NOT NULL, factor DOUBLE PRECISION NOT NULL,
        UNIQUE(anio_rentas, mes)
);

CREATE TABLE IF NOT EXISTS feriados (
        fecha DATE PRIMARY KEY, nombre TEXT
);

CREATE TABLE IF NOT EXISTS liquidaciones (
        id BIGSERIAL PRIMARY KEY, empresa_id INTEGER NOT NULL REFERENCES empresas(id),
        trabajador_id INTEGER NOT NULL REFERENCES trabajadores(id), contrato_id INTEGER,
        periodo TEXT NOT NULL, dias_trabajados INTEGER DEFAULT 30,
        horas_extras DOUBLE PRECISION DEFAULT 0, monto_horas_extras DOUBLE PRECISION DEFAULT 0,
        sueldo_base DOUBLE PRECISION, sueldo_calculado DOUBLE PRECISION, gratificacion DOUBLE PRECISION, movilizacion DOUBLE PRECISION,
        colacion DOUBLE PRECISION, asignacion_familiar DOUBLE PRECISION DEFAULT 0, otros_haberes DOUBLE PRECISION,
        total_haberes DOUBLE PRECISION, total_imponible DOUBLE PRECISION, afp_monto DOUBLE PRECISION, salud_monto DOUBLE PRECISION,
        salud_fonasa DOUBLE PRECISION DEFAULT 0, salud_ccaf DOUBLE PRECISION DEFAULT 0, adicional_isapre DOUBLE PRECISION,
        sis_monto DOUBLE PRECISION, afc_trabajador DOUBLE PRECISION, afc_empleador DOUBLE PRECISION, mutual_monto DOUBLE PRECISION,
        reforma_afp_emp DOUBLE PRECISION DEFAULT 0, reforma_crp DOUBLE PRECISION DEFAULT 0,
        reforma_seguro_social DOUBLE PRECISION DEFAULT 0, base_tributable DOUBLE PRECISION,
        impuesto_unico DOUBLE PRECISION DEFAULT 0, anticipo DOUBLE PRECISION DEFAULT 0,
        aguinaldo DOUBLE PRECISION DEFAULT 0, bonos_imponibles DOUBLE PRECISION DEFAULT 0, haberes_no_imponibles DOUBLE PRECISION DEFAULT 0,
        otros_descuentos DOUBLE PRECISION DEFAULT 0, dias_licencia DOUBLE PRECISION DEFAULT 0, dias_vacaciones DOUBLE PRECISION DEFAULT 0,
        detalle TEXT,
        total_descuentos DOUBLE PRECISION, liquido DOUBLE PRECISION, tramo_asignacion TEXT, advertencias TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(empresa_id, trabajador_id, periodo)
);

CREATE TABLE IF NOT EXISTS vacaciones (
        id BIGSERIAL PRIMARY KEY, trabajador_id INTEGER NOT NULL REFERENCES trabajadores(id),
        empresa_id INTEGER NOT NULL REFERENCES empresas(id), fecha_inicio DATE, fecha_termino DATE,
        dias_habiles DOUBLE PRECISION, dias_corridos DOUBLE PRECISION, tipo TEXT DEFAULT 'Legales', periodo_devengo TEXT,
        comprobante_generado INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS finiquitos (
        id BIGSERIAL PRIMARY KEY, trabajador_id INTEGER NOT NULL REFERENCES trabajadores(id),
        empresa_id INTEGER NOT NULL REFERENCES empresas(id), contrato_id INTEGER,
        fecha_termino DATE NOT NULL, causal TEXT, causal_codigo INTEGER, aviso_dado INTEGER DEFAULT 0,
        base_calculo DOUBLE PRECISION, base_con_tope DOUBLE PRECISION, anos_pagar INTEGER DEFAULT 0,
        vacaciones_proporcionales_dias DOUBLE PRECISION, vacaciones_proporcionales_monto DOUBLE PRECISION,
        feriado_dias_corridos DOUBLE PRECISION, valor_dia_feriado DOUBLE PRECISION,
        indemnizacion_anos DOUBLE PRECISION DEFAULT 0, aviso_previo DOUBLE PRECISION DEFAULT 0,
        descuento_afc DOUBLE PRECISION DEFAULT 0, otros_montos DOUBLE PRECISION DEFAULT 0, otros_descuentos DOUBLE PRECISION DEFAULT 0,
        total_finiquito DOUBLE PRECISION, observaciones TEXT, detalle TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS periodos_rrhh (
        id BIGSERIAL PRIMARY KEY, empresa_id INTEGER NOT NULL REFERENCES empresas(id), periodo TEXT NOT NULL,
        estado TEXT DEFAULT 'Abierto', enviado_por TEXT, enviado_at TIMESTAMP,
        UNIQUE(empresa_id, periodo)
);

CREATE TABLE IF NOT EXISTS conceptos (
        id BIGSERIAL PRIMARY KEY, empresa_id INTEGER NOT NULL REFERENCES empresas(id), nombre TEXT NOT NULL,
        tipo TEXT DEFAULT 'Haber imponible', codigo_lre INTEGER, activo INTEGER DEFAULT 1, orden INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS movimientos (
        id BIGSERIAL PRIMARY KEY, empresa_id INTEGER NOT NULL REFERENCES empresas(id),
        trabajador_id INTEGER NOT NULL REFERENCES trabajadores(id), periodo TEXT NOT NULL,
        dias_trabajados DOUBLE PRECISION, ausencias DOUBLE PRECISION DEFAULT 0, licencia DOUBLE PRECISION DEFAULT 0,
        licencia_desde DATE, licencia_hasta DATE, dias_vacaciones DOUBLE PRECISION DEFAULT 0,
        anticipo DOUBLE PRECISION DEFAULT 0, aguinaldo DOUBLE PRECISION DEFAULT 0, bono_desempeno DOUBLE PRECISION DEFAULT 0,
        cant_he_50 DOUBLE PRECISION DEFAULT 0, cant_he_100 DOUBLE PRECISION DEFAULT 0, cant_hd DOUBLE PRECISION DEFAULT 0, cant_hed DOUBLE PRECISION DEFAULT 0,
        valor_he_50 DOUBLE PRECISION DEFAULT 0, valor_he_100 DOUBLE PRECISION DEFAULT 0, valor_hd DOUBLE PRECISION DEFAULT 0, valor_hed DOUBLE PRECISION DEFAULT 0,
        colacion DOUBLE PRECISION DEFAULT 0, movilizacion DOUBLE PRECISION DEFAULT 0, extras TEXT, observacion TEXT,
        updated_by TEXT, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(empresa_id, trabajador_id, periodo)
);

CREATE TABLE IF NOT EXISTS usuarios (
        id BIGSERIAL PRIMARY KEY, usuario TEXT UNIQUE NOT NULL, nombre TEXT, hash TEXT NOT NULL, salt TEXT NOT NULL,
        rol TEXT DEFAULT 'usuario', empresas TEXT DEFAULT '[]', modulos TEXT DEFAULT '["remuneraciones"]',
        activo INTEGER DEFAULT 1,
        dias_acceso INTEGER, fecha_expira DATE, primer_acceso DATE, ultimo_acceso DATE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS configuracion (
        clave TEXT PRIMARY KEY, valor TEXT
);

CREATE TABLE IF NOT EXISTS documentos_trabajador (
        id BIGSERIAL PRIMARY KEY, empresa_id INTEGER NOT NULL REFERENCES empresas(id),
        trabajador_id INTEGER NOT NULL REFERENCES trabajadores(id), tipo TEXT NOT NULL, periodo TEXT, fecha DATE,
        descripcion TEXT, nombre_archivo TEXT NOT NULL, mime TEXT, tamano INTEGER, contenido BYTEA NOT NULL,
        origen TEXT DEFAULT 'generado', ref_tabla TEXT, ref_id INTEGER, creado_por TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS anexos_contrato (
        id BIGSERIAL PRIMARY KEY, contrato_id INTEGER NOT NULL REFERENCES contratos(id), empresa_id INTEGER NOT NULL REFERENCES empresas(id),
        trabajador_id INTEGER NOT NULL REFERENCES trabajadores(id), fecha DATE, vigencia DATE, cambios TEXT,
        documento_id INTEGER, creado_por TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
