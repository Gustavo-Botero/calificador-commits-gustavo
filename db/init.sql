-- Tabla donde se registran todas las inferencias
CREATE TABLE IF NOT EXISTS inferencias (
    id          SERIAL PRIMARY KEY,
    fecha       TIMESTAMP NOT NULL DEFAULT NOW(),
    motor       VARCHAR(20)  NOT NULL,
    modelo      VARCHAR(120) NOT NULL,
    entrada     TEXT NOT NULL,
    salida      TEXT NOT NULL,
    latencia_ms INTEGER NOT NULL
);

-- Rol de aplicacion con privilegios minimos
CREATE ROLE app_ia WITH LOGIN PASSWORD 'claveApp456';
GRANT CONNECT ON DATABASE iadb TO app_ia;
GRANT USAGE ON SCHEMA public TO app_ia;
GRANT SELECT, INSERT ON inferencias TO app_ia;
GRANT USAGE, SELECT ON SEQUENCE inferencias_id_seq TO app_ia;
