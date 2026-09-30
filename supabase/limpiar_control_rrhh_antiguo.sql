-- OPCIONAL. Ejecutar en Supabase (proyecto Control RRHH → SQL Editor) SOLO cuando el módulo RRHH de BASECON
-- esté funcionando y ya no se use el index.html de Control RRHH. Borra las tablas antiguas de prueba del
-- schema public. No toca el schema "basecon", donde están los datos de BASECON.
drop table if exists public.rem_liquidaciones, public.rem_finiquitos, public.rem_contratos,
  public.rem_indicadores, public.rem_factores_actualizacion cascade;
drop table if exists public.entries, public.periodos, public.conceptos, public.empresa_members,
  public.trabajadores, public.empresas, public.admins cascade;
-- Si aparecen otras tablas rem_* no listadas arriba, revíselas y bórrelas de la misma forma.
