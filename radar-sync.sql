-- 서울 신상 레이더: 기기끼리 '어디까지 봤나'를 맞추는 표
--
-- 일진일기와 같은 Supabase 프로젝트의 SQL Editor에 통째로 붙여넣고 실행하면 된다.
-- 몇 번을 다시 돌려도 괜찮게 짰다. 일진일기의 표(records·vault)는 건드리지 않는다.
--
-- 담는 것은 탭별 마지막으로 본 날·NEW 기준일, '놓친 곳'을 다 봤는지, 숨긴 블로그 글뿐이다.
-- key 예: seoul-radar:baseline, value 예: 2026-10-20

create table if not exists public.radar_state (
  user_id     uuid        not null references auth.users(id) on delete cascade,
  key         text        not null,
  value       text        not null,
  updated_at  timestamptz not null default now(),
  primary key (user_id, key)
);

-- anon 키는 공개 값이라, 남의 기록을 못 보게 막는 것은 아래 정책들이다.
alter table public.radar_state enable row level security;

drop policy if exists "본인 레이더 기록만 읽는다" on public.radar_state;
drop policy if exists "본인 레이더 기록만 넣는다" on public.radar_state;
drop policy if exists "본인 레이더 기록만 고친다" on public.radar_state;
drop policy if exists "본인 레이더 기록만 지운다" on public.radar_state;

create policy "본인 레이더 기록만 읽는다" on public.radar_state
  for select using (auth.uid() = user_id);
create policy "본인 레이더 기록만 넣는다" on public.radar_state
  for insert with check (auth.uid() = user_id);
create policy "본인 레이더 기록만 고친다" on public.radar_state
  for update using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "본인 레이더 기록만 지운다" on public.radar_state
  for delete using (auth.uid() = user_id);
