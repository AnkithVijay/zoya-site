-- Advisor 0028/0029: the project's built-in rls_auto_enable() event-trigger helper is
-- SECURITY DEFINER and executable by anon/authenticated. It only needs to run from its
-- event trigger, so revoke API execute.
revoke execute on function public.rls_auto_enable() from public, anon, authenticated;
