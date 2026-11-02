create table if not exists public.tracked_exams (
  id uuid primary key default gen_random_uuid(),
  exam_key text not null unique,
  exam_name text not null,
  organisation text,
  cycle_label text,
  official_url text,
  is_following boolean not null default true,
  lifecycle_status text not null default 'active'
    check (lifecycle_status in ('active','result_declared','archived')),
  first_seen_at timestamptz not null default now(),
  last_update_at timestamptz not null default now(),
  result_declared_at timestamptz,
  archive_after timestamptz,
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists tracked_exams_following_idx
  on public.tracked_exams (is_following, lifecycle_status, last_update_at desc);

create table if not exists public.exam_updates (
  id text primary key,
  title text not null,
  post_type text not null,
  exam_name text,
  organisation text,
  source_name text,
  source_title text,
  source_url text not null,
  source_page_url text,
  source_sha256 text,
  attachment_path text,
  attachment_url text,
  attachment_name text,
  attachment_mime_type text,
  result_url text,
  summary text,
  detected_at timestamptz not null default now(),
  review_status text not null default 'pending_review'
    check (review_status in ('pending_review','verified','published','rejected','archived')),
  human_verified boolean not null default false,
  published_at timestamptz,
  result_declared boolean not null default false,
  facts jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists exam_updates_detected_idx
  on public.exam_updates (detected_at desc);
create index if not exists exam_updates_review_idx
  on public.exam_updates (review_status, detected_at desc);
create index if not exists exam_updates_source_hash_idx
  on public.exam_updates (source_sha256);

create table if not exists public.exam_update_exams (
  update_id text not null references public.exam_updates(id) on delete cascade,
  exam_id uuid not null references public.tracked_exams(id) on delete cascade,
  primary key (update_id, exam_id)
);
create index if not exists exam_update_exams_exam_idx
  on public.exam_update_exams (exam_id, update_id);

alter table public.tracked_exams enable row level security;
alter table public.exam_updates enable row level security;
alter table public.exam_update_exams enable row level security;

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

revoke all on public.tracked_exams, public.exam_updates, public.exam_update_exams from anon;
grant select, insert, update, delete on public.tracked_exams, public.exam_updates, public.exam_update_exams to authenticated, service_role;

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
  'official-updates',
  'official-updates',
  true,
  26214400,
  array[
    'application/pdf',
    'application/zip',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'text/csv'
  ]
)
on conflict (id) do update
set public = excluded.public,
    file_size_limit = excluded.file_size_limit,
    allowed_mime_types = excluded.allowed_mime_types;

drop policy if exists "Public can read official update attachments" on storage.objects;
create policy "Public can read official update attachments" on storage.objects
  for select to anon, authenticated
  using (bucket_id = 'official-updates');
