-- Acceso de solo lectura para el gateway de datos (autenticación de Windows).
-- Ejecutar DESPUÉS de instalar el gateway, con una cuenta administradora de SQL Server:
--   python tools/onprem_gateway_acceso.py [--cuenta "NT SERVICE\PBIEgwService"]
--
-- El gateway consulta SQL con la cuenta de su servicio; la contraseña no interviene.
-- Limitación: todos los usuarios de Power Apps pasan por esta única identidad, así que
-- SQL Server no distingue áreas. Por eso se le dan las vistas de todas las áreas y la
-- separación por área se aplica en la app.
-- Los marcadores {CUENTA} y {BD} los reemplaza la herramienta.

IF SUSER_ID(N'{CUENTA}') IS NULL
    CREATE LOGIN [{CUENTA}] FROM WINDOWS;
GO
USE [{BD}];
IF DATABASE_PRINCIPAL_ID(N'{CUENTA}') IS NULL
    CREATE USER [{CUENTA}] FOR LOGIN [{CUENTA}];
GO
-- Solo lectura sobre las vistas: ninguna tabla ni escritura.
ALTER ROLE rol_hub_consulta ADD MEMBER [{CUENTA}];
ALTER ROLE rol_hub_bi ADD MEMBER [{CUENTA}];
DECLARE @i int = 1, @s nvarchar(300);
WHILE @i <= 10 BEGIN
    SET @s = N'ALTER ROLE rol_hub_area' + RIGHT('0' + CAST(@i AS varchar(2)), 2) + N' ADD MEMBER [{CUENTA}]';
    EXEC sys.sp_executesql @s;
    SET @i += 1;
END
GO
