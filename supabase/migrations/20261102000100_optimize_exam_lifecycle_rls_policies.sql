drop policy if exists "Admins manage tracked exams" on public.tracked_exams;
create policy "Admins manage tracked exams" on public.tracked_exams
  for all to authenticated
  using (((select auth.jwt())->'app_metadata'->>'role') = 'admin')
  with check (((select auth.jwt())->'app_metadata'->>'role') = 'admin');

drop policy if exists "Admins manage exam updates" on public.exam_updates;
create policy "Admins manage exam updates" on public.exam_updates
  for all to authenticated
  using (((select auth.jwt())->'app_metadata'->>'role') = 'admin')
  with check (((select auth.jwt())->'app_metadata'->>'role') = 'admin');

drop policy if exists "Admins manage exam update links" on public.exam_update_exams;
create policy "Admins manage exam update links" on public.exam_update_exams
  for all to authenticated
  using (((select auth.jwt())->'app_metadata'->>'role') = 'admin')
  with check (((select auth.jwt())->'app_metadata'->>'role') = 'admin');
