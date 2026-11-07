-- Vistas de observaciones por área (11.6) y roles de base de datos con
-- permisos mínimos. Los usuarios Entra se agregan a estos roles en
-- 900_usuarios_azure.sql (solo Azure SQL).

DECLARE @i int=1,@s nvarchar(max);
WHILE @i<=10
BEGIN
 SET @s=N'CREATE OR ALTER VIEW dbo.vObservaciones'+RIGHT('0'+CAST(@i AS varchar(2)),2)+N' AS
SELECT o.ObservacionId,o.LoteId,o.FilaExcel,o.Campo,o.Codigo,o.Mensaje,
 l.Estado AS EstadoLote,l.CreadoUtc,l.VersionFuente,
 CAST(CASE WHEN o.SubsanadaPor IS NULL THEN 0 ELSE 1 END AS bit) AS Subsanada,
 o.SubsanadaPor
FROM dbo.Observacion o JOIN dbo.Lote l ON l.LoteId=o.LoteId
WHERE l.AreaId='+CAST(@i AS nvarchar(2))+N';';
 EXEC sys.sp_executesql @s;
 SET @i+=1;
END
GO

-- Roles (se crean solo si no existen para que el script sea repetible)
DECLARE @roles TABLE (n sysname);
INSERT @roles VALUES ('rol_hub_consulta'),('rol_hub_integracion'),
 ('rol_hub_ingesta_base'),('rol_hub_bi'),('rol_hub_avisos');
DECLARE @i int=1;
WHILE @i<=10 BEGIN
 INSERT @roles VALUES ('rol_hub_area'+RIGHT('0'+CAST(@i AS varchar(2)),2));
 SET @i+=1;
END
DECLARE @n sysname,@s nvarchar(400);
DECLARE c CURSOR LOCAL FAST_FORWARD FOR SELECT n FROM @roles;
OPEN c; FETCH NEXT FROM c INTO @n;
WHILE @@FETCH_STATUS=0 BEGIN
 IF DATABASE_PRINCIPAL_ID(@n) IS NULL BEGIN
  SET @s=N'CREATE ROLE '+QUOTENAME(@n);
  EXEC sys.sp_executesql @s;
 END
 FETCH NEXT FROM c INTO @n;
END
CLOSE c; DEALLOCATE c;
GO

-- Ventanilla / app ConsultaDeuda: solo vistas autorizadas (11.1).
GRANT SELECT ON dbo.vDeuda TO rol_hub_consulta;
GRANT SELECT ON dbo.vEstadoFuentes TO rol_hub_consulta;
GRANT SELECT ON dbo.vMovimientoDetalle TO rol_hub_consulta;

-- Cada área ve solo su vista de observaciones (prueba T12).
DECLARE @i int=1,@s nvarchar(400);
WHILE @i<=10 BEGIN
 SET @s=N'GRANT SELECT ON dbo.vObservaciones'+RIGHT('0'+CAST(@i AS varchar(2)),2)
  +N' TO rol_hub_area'+RIGHT('0'+CAST(@i AS varchar(2)),2);
 EXEC sys.sp_executesql @s;
 SET @i+=1;
END
GO

-- Function (procesamiento de Excel): lee catálogos y base vigente,
-- inserta lotes/movimientos/observaciones/avisos y publica vía procedimiento.
GRANT SELECT ON dbo.Area TO rol_hub_integracion;
GRANT SELECT ON dbo.AreaFuente TO rol_hub_integracion;
GRANT SELECT ON dbo.vBaseVigente TO rol_hub_integracion;
GRANT SELECT, INSERT ON dbo.Lote TO rol_hub_integracion;
GRANT SELECT, INSERT ON dbo.Movimiento TO rol_hub_integracion;
GRANT SELECT, INSERT ON dbo.Observacion TO rol_hub_integracion;
GRANT INSERT ON dbo.Notificacion TO rol_hub_integracion;
GRANT SELECT, INSERT, UPDATE ON dbo.ProcesoManifiesto TO rol_hub_integracion;
GRANT EXECUTE ON dbo.usp_PublicarArea TO rol_hub_integracion;

-- Data Factory (deuda base): solo ingesta y publicación de la fotografía.
GRANT INSERT ON dbo.BaseFila TO rol_hub_ingesta_base;
GRANT EXECUTE ON dbo.usp_IniciarBaseCarga TO rol_hub_ingesta_base;
GRANT EXECUTE ON dbo.usp_PublicarBase TO rol_hub_ingesta_base;
GRANT EXECUTE ON dbo.usp_MarcarBaseFallida TO rol_hub_ingesta_base;

-- Power BI: vistas de lectura, sin tablas operativas.
GRANT SELECT ON dbo.vDeuda TO rol_hub_bi;
GRANT SELECT ON dbo.vEstadoFuentes TO rol_hub_bi;
GRANT SELECT ON dbo.vMovimientoDetalle TO rol_hub_bi;
GRANT SELECT ON dbo.vLoteCalidad TO rol_hub_bi;
GRANT SELECT ON dbo.vObservacionCalidad TO rol_hub_bi;
GRANT SELECT ON dbo.Area TO rol_hub_bi;

-- Flujo de avisos: toma pendientes y marca enviados.
GRANT SELECT, UPDATE ON dbo.Notificacion TO rol_hub_avisos;
GRANT SELECT ON dbo.vLoteCalidad TO rol_hub_avisos;
GRANT SELECT ON dbo.AreaFuente TO rol_hub_avisos;
GO
