-- Vistas de consulta (Anexo A) y vistas adicionales para apps y Power BI.
CREATE OR ALTER VIEW dbo.vMovimientoVigente AS
SELECT a.AreaId,m.LoteId,m.MovimientoId,m.PapeletaId,m.Tipo,m.Monto,
 m.FechaEvento,m.Estado,m.Referencia,m.Detalle,m.FilaExcel
FROM dbo.Area a
JOIN dbo.Movimiento m ON m.LoteId=a.LoteVigente;
GO
CREATE OR ALTER VIEW dbo.vBaseVigente AS
SELECT b.CargaId,b.PapeletaId,b.TipoDoc,b.Documento,b.Placa,
 b.ImporteOriginal,b.Activa,c.CorteUtc
FROM dbo.BaseActual a
JOIN dbo.BaseFila b ON b.CargaId=a.CargaId
JOIN dbo.BaseCarga c ON c.CargaId=b.CargaId;
GO
-- Saldo = ImporteOriginal + movimientos activos con signo (2.2).
-- Puede ser negativo (pago en exceso): se muestra, no se oculta.
CREATE OR ALTER VIEW dbo.vDeuda AS
WITH S AS (
 SELECT PapeletaId,
 SUM(CASE WHEN Estado='ANULADO' THEN 0
          WHEN Tipo IN ('PAGO','DESCUENTO') THEN -Monto
          WHEN Tipo='CARGO' THEN Monto ELSE 0 END) Ajuste
 FROM dbo.vMovimientoVigente GROUP BY PapeletaId
)
SELECT b.PapeletaId,b.TipoDoc,b.Documento,
 CAST(LEFT(b.Documento,2)+REPLICATE('*',LEN(b.Documento)-4)
      +RIGHT(b.Documento,2) AS varchar(11)) AS DocumentoEnmascarado,
 b.Placa,b.ImporteOriginal,CAST(COALESCE(s.Ajuste,0) AS decimal(18,2)) AS Movimientos,
 CAST(b.ImporteOriginal+COALESCE(s.Ajuste,0) AS decimal(18,2)) AS Saldo,
 CAST(CASE WHEN b.ImporteOriginal+COALESCE(s.Ajuste,0)<0 THEN 1 ELSE 0 END AS bit)
   AS RequiereRevision,
 b.Activa,b.CorteUtc
FROM dbo.vBaseVigente b
LEFT JOIN S s ON s.PapeletaId=b.PapeletaId;
GO
-- Detalle por papeleta para la pantalla Detalle y el reporte PDF.
CREATE OR ALTER VIEW dbo.vMovimientoDetalle AS
SELECT m.PapeletaId,m.AreaId,a.Nombre AS Area,m.MovimientoId,m.Tipo,
 m.Monto,m.Estado,m.FechaEvento,m.Referencia,m.LoteId,l.PublicadoUtc
FROM dbo.vMovimientoVigente m
JOIN dbo.Area a ON a.AreaId=m.AreaId
JOIN dbo.Lote l ON l.LoteId=m.LoteId;
GO
-- Frescura por fuente: versión aceptada y última verificación exitosa
-- (incluye SIN_CAMBIOS). La base se reporta como AreaId 0.
CREATE OR ALTER VIEW dbo.vEstadoFuentes AS
SELECT a.AreaId,a.Nombre,l.LoteId,l.ModificadoUtc,
 l.PublicadoUtc,l.Estado,v.UltimaVerificacionUtc,u.UltimoIntentoUtc,u.UltimoEstado
FROM dbo.Area a LEFT JOIN dbo.Lote l
 ON l.LoteId=a.LoteVigente
OUTER APPLY (
 SELECT MAX(CreadoUtc) UltimaVerificacionUtc FROM dbo.Lote x
 WHERE x.AreaId=a.AreaId
 AND x.Estado IN ('ACEPTADO','SIN_CAMBIOS')
) v
OUTER APPLY (
 SELECT TOP 1 y.CreadoUtc UltimoIntentoUtc,y.Estado UltimoEstado
 FROM dbo.Lote y WHERE y.AreaId=a.AreaId ORDER BY y.CreadoUtc DESC
) u
UNION ALL
SELECT CAST(0 AS tinyint),N'Base de deuda (origen local)',c.CargaId,c.CorteUtc,
 c.PublicadaUtc,c.Estado,c.PublicadaUtc,z.UltimoIntentoUtc,z.UltimoEstado
FROM dbo.BaseActual b
LEFT JOIN dbo.BaseCarga c ON c.CargaId=b.CargaId
OUTER APPLY (
 SELECT TOP 1 w.CreadaUtc UltimoIntentoUtc,w.Estado UltimoEstado
 FROM dbo.BaseCarga w ORDER BY w.CreadaUtc DESC
) z;
GO
-- Lotes con métricas de calidad para Power BI (filas distintas con error).
CREATE OR ALTER VIEW dbo.vLoteCalidad AS
SELECT l.LoteId,l.AreaId,a.Nombre AS Area,l.Estado,l.FilasLeidas,
 l.CreadoUtc,l.PublicadoUtc,
 DATEDIFF(SECOND,l.CreadoUtc,COALESCE(l.PublicadoUtc,l.CreadoUtc)) AS SegundosPublicacion,
 (SELECT COUNT(*) FROM dbo.Observacion o WHERE o.LoteId=l.LoteId) AS Errores,
 (SELECT COUNT(DISTINCT o.FilaExcel) FROM dbo.Observacion o
   WHERE o.LoteId=l.LoteId AND o.FilaExcel>0) AS FilasConError
FROM dbo.Lote l JOIN dbo.Area a ON a.AreaId=l.AreaId;
GO
CREATE OR ALTER VIEW dbo.vObservacionCalidad AS
SELECT o.ObservacionId,o.LoteId,l.AreaId,o.FilaExcel,o.Campo,o.Codigo,
 l.CreadoUtc,CAST(CASE WHEN o.SubsanadaPor IS NULL THEN 0 ELSE 1 END AS bit) AS Subsanada
FROM dbo.Observacion o JOIN dbo.Lote l ON l.LoteId=o.LoteId;
GO
