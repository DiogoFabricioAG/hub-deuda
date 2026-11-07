-- La Function comprueba si el aviso ya existe antes de insertarlo
-- (repositorio_sql.insertar_notificacion): necesita SELECT además de INSERT.
-- Detectado en la prueba de humo en Azure (error 229, 2026-11-07).
GRANT SELECT ON dbo.Notificacion TO rol_hub_integracion;
GO
