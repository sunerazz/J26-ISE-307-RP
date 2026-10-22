-- Run this once in the Supabase SQL editor.
-- Then enable Authentication → Sign In / Providers → Anonymous Sign-Ins.

create table if not exists public.driver_profiles (
  user_id uuid primary key references auth.users (id) on delete cascade,
  reserve_percent double precision not null default 10,
  scenario_tariff_lkr double precision,
  charging_efficiency double precision,
  updated_at timestamptz not null default now()
);

create table if not exists public.saved_trips (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  created_at timestamptz not null default now(),
  origin_name text not null,
  destination_name text not null,
  station_id text,
  station_name text,
  summary text not null default ''
);

alter table public.driver_profiles enable row level security;
alter table public.saved_trips enable row level security;

drop policy if exists "driver reads own profile" on public.driver_profiles;
drop policy if exists "driver writes own profile" on public.driver_profiles;
drop policy if exists "driver updates own profile" on public.driver_profiles;
drop policy if exists "driver reads own trips" on public.saved_trips;
drop policy if exists "driver writes own trips" on public.saved_trips;

create policy "driver reads own profile"
  on public.driver_profiles for select
  using (auth.uid() = user_id);

create policy "driver writes own profile"
  on public.driver_profiles for insert
  with check (auth.uid() = user_id);

create policy "driver updates own profile"
  on public.driver_profiles for update
  using (auth.uid() = user_id)
  with check (auth.uid() = user_id);

create policy "driver reads own trips"
  on public.saved_trips for select
  using (auth.uid() = user_id);

create policy "driver inserts own trips"
  on public.saved_trips for insert
  with check (auth.uid() = user_id);

create policy "driver deletes own trips"
  on public.saved_trips for delete
  using (auth.uid() = user_id);
