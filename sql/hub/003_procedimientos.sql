-- Procedimientos de publicación (Anexo A) y de soporte para ADF y administración.

-- ADF: registrar la fotografía antes de Copy (8.4). Idempotente por CargaId.
CREATE OR ALTER PROCEDURE dbo.usp_IniciarBaseCarga
 @CargaId uniqueidentifier,
 @CorteUtc datetime2,
 @FilasEsperadas int
AS
BEGIN
 SET NOCOUNT ON; SET XACT_ABORT ON;
 IF EXISTS (SELECT 1 FROM dbo.BaseCarga WHERE CargaId=@CargaId)
 BEGIN
  IF EXISTS (SELECT 1 FROM dbo.BaseCarga WHERE CargaId=@CargaId AND Estado<>'RECIBIDA')
   THROW 50010,'La carga ya terminó; no se reutiliza su CargaId',1;
  RETURN;
 END
 INSERT dbo.BaseCarga (CargaId,CorteUtc,Estado,FilasEsperadas)
 VALUES (@CargaId,@CorteUtc,'RECIBIDA',@FilasEsperadas);
END;
GO

CREATE OR ALTER PROCEDURE dbo.usp_PublicarBase
 @CargaId uniqueidentifier
AS
BEGIN
 SET NOCOUNT ON; SET XACT_ABORT ON;
 BEGIN TRY
  BEGIN TRAN;
  DECLARE @r int,@n int,@c datetime2;
  EXEC @r=sys.sp_getapplock @Resource='PublicacionHub',
   @LockMode='Exclusive',@LockOwner='Transaction',
   @LockTimeout=10000;
  IF @r<0 THROW 50001,'No se obtuvo bloqueo',1;
  SELECT @n=FilasEsperadas,@c=CorteUtc FROM dbo.BaseCarga
   WHERE CargaId=@CargaId AND Estado='RECIBIDA';
  IF @n IS NULL OR @n<=0
   THROW 50002,'Carga ausente o vacia',1;
  IF (SELECT COUNT(*) FROM dbo.BaseFila
      WHERE CargaId=@CargaId)<>@n
   THROW 50003,'Conteo de origen y destino distinto',1;
  IF EXISTS (SELECT 1 FROM dbo.BaseFila WHERE CargaId=@CargaId
   AND (Documento LIKE '%[^0-9]%' OR
    LEN(Documento)<>CASE TipoDoc WHEN 'DNI' THEN 8 ELSE 11 END))
   THROW 50004,'Documento invalido',1;
  IF EXISTS (SELECT 1 FROM dbo.vMovimientoVigente m
   WHERE NOT EXISTS (SELECT 1 FROM dbo.BaseFila b
    WHERE b.CargaId=@CargaId AND b.PapeletaId=m.PapeletaId))
   THROW 50005,'La base omite deudas con movimientos',1;
  IF EXISTS (SELECT 1 FROM dbo.BaseActual a
   JOIN dbo.BaseCarga c ON c.CargaId=a.CargaId
   WHERE c.CorteUtc>=@c)
   THROW 50006,'Corte obsoleto',1;
  UPDATE dbo.BaseActual SET CargaId=@CargaId WHERE Id=1;
  UPDATE dbo.BaseCarga SET Estado='ACEPTADA',
   PublicadaUtc=SYSUTCDATETIME() WHERE CargaId=@CargaId;
  COMMIT;
 END TRY
 BEGIN CATCH
  IF @@TRANCOUNT>0 ROLLBACK;
  THROW;
 END CATCH
END;
GO

-- ADF, rama de error: marca FALLIDA sin tocar el puntero (8.5).
CREATE OR ALTER PROCEDURE dbo.usp_MarcarBaseFallida
 @CargaId uniqueidentifier,
 @Motivo nvarchar(500)
AS
BEGIN
 SET NOCOUNT ON;
 UPDATE dbo.BaseCarga SET Estado='FALLIDA',Motivo=LEFT(@Motivo,500)
 WHERE CargaId=@CargaId AND Estado='RECIBIDA';
END;
GO

CREATE OR ALTER PROCEDURE dbo.usp_PublicarArea
 @LoteId uniqueidentifier
AS
BEGIN
 SET NOCOUNT ON;
 IF @@TRANCOUNT=0 THROW 50101,'Se requiere transaccion',1;
 DECLARE @r int,@a tinyint,@v uniqueidentifier,@f datetime2;
 EXEC @r=sys.sp_getapplock @Resource='PublicacionHub',
  @LockMode='Exclusive',@LockOwner='Transaction',
  @LockTimeout=10000;
 IF @r<0 THROW 50102,'No se obtuvo bloqueo',1;
 SELECT @a=AreaId,@f=ModificadoUtc FROM dbo.Lote
  WHERE LoteId=@LoteId AND Estado='VALIDADO';
 IF @a IS NULL THROW 50103,'Lote no validado',1;
 SELECT @v=LoteVigente FROM dbo.Area WHERE AreaId=@a;
 IF EXISTS (SELECT 1 FROM dbo.Lote WHERE LoteId=@v
            AND ModificadoUtc>=@f)
  THROW 50104,'Version obsoleta',1;
 IF EXISTS (SELECT 1 FROM dbo.Observacion WHERE LoteId=@LoteId)
  THROW 50105,'Lote con observaciones',1;
 IF NOT EXISTS (SELECT 1 FROM dbo.Movimiento WHERE LoteId=@LoteId)
  THROW 50105,'Lote vacio no autorizado',1;
 IF (SELECT COUNT(*) FROM dbo.Movimiento WHERE LoteId=@LoteId)
   <> (SELECT FilasLeidas FROM dbo.Lote WHERE LoteId=@LoteId)
  THROW 50105,'Lote incompleto',1;
 IF EXISTS (SELECT 1 FROM dbo.Movimiento m WHERE m.LoteId=@LoteId
  AND NOT EXISTS (SELECT 1 FROM dbo.vBaseVigente b
                  WHERE b.PapeletaId=m.PapeletaId))
  THROW 50106,'Papeleta inexistente',1;
 IF EXISTS (SELECT 1 FROM dbo.Movimiento m WHERE m.LoteId=@v
  AND NOT EXISTS (SELECT 1 FROM dbo.Movimiento n
   WHERE n.LoteId=@LoteId AND n.MovimientoId=m.MovimientoId))
  THROW 50107,'No se permite omitir movimientos anteriores',1;
 IF EXISTS (SELECT 1 FROM dbo.Movimiento m JOIN dbo.Area a
  ON a.AreaId=@a WHERE m.LoteId=@LoteId
   AND m.Tipo NOT IN ('OBSERVACION',a.TipoPermitido))
  THROW 50105,'Tipo no autorizado para el area',1;
 UPDATE dbo.Area SET LoteVigente=@LoteId WHERE AreaId=@a;
 UPDATE dbo.Lote SET Estado='ACEPTADO',PublicadoUtc=SYSUTCDATETIME()
  WHERE LoteId=@LoteId;
 -- 11.9: las observaciones de lotes anteriores del área quedan subsanadas.
 UPDATE o SET SubsanadaPor=@LoteId
 FROM dbo.Observacion o JOIN dbo.Lote l ON l.LoteId=o.LoteId
 WHERE l.AreaId=@a AND l.LoteId<>@LoteId AND o.SubsanadaPor IS NULL;
END;
GO

-- 15.4: restaurar el puntero de un área a un lote aceptado, con motivo auditado.
CREATE TABLE dbo.CambioPuntero (
 CambioId bigint IDENTITY PRIMARY KEY,
 AreaId tinyint NOT NULL REFERENCES dbo.Area(AreaId),
 Anterior uniqueidentifier NULL,
 Nuevo uniqueidentifier NOT NULL,
 Motivo nvarchar(500) NOT NULL,
 Usuario sysname NOT NULL DEFAULT ORIGINAL_LOGIN(),
 FechaUtc datetime2 NOT NULL DEFAULT SYSUTCDATETIME()
);
GO
CREATE OR ALTER PROCEDURE dbo.usp_RestaurarLoteVigente
 @AreaId tinyint,
 @LoteId uniqueidentifier,
 @Motivo nvarchar(500)
AS
BEGIN
 SET NOCOUNT ON; SET XACT_ABORT ON;
 IF LEN(LTRIM(RTRIM(COALESCE(@Motivo,''))))<10
  THROW 50201,'Indique un motivo de al menos 10 caracteres',1;
 BEGIN TRAN;
 DECLARE @r int,@v uniqueidentifier;
 EXEC @r=sys.sp_getapplock @Resource='PublicacionHub',
  @LockMode='Exclusive',@LockOwner='Transaction',@LockTimeout=10000;
 IF @r<0 THROW 50202,'No se obtuvo bloqueo',1;
 IF NOT EXISTS (SELECT 1 FROM dbo.Lote WHERE LoteId=@LoteId
                AND AreaId=@AreaId AND Estado='ACEPTADO')
  THROW 50203,'El lote no es una version aceptada del area',1;
 SELECT @v=LoteVigente FROM dbo.Area WHERE AreaId=@AreaId;
 IF EXISTS (SELECT 1 FROM dbo.Movimiento m WHERE m.LoteId=@LoteId
  AND NOT EXISTS (SELECT 1 FROM dbo.vBaseVigente b WHERE b.PapeletaId=m.PapeletaId))
  THROW 50204,'El lote referencia papeletas fuera de la base vigente',1;
 UPDATE dbo.Area SET LoteVigente=@LoteId WHERE AreaId=@AreaId;
 INSERT dbo.CambioPuntero (AreaId,Anterior,Nuevo,Motivo)
 VALUES (@AreaId,@v,@LoteId,@Motivo);
 COMMIT;
END;
GO
