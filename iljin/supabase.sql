-- 일진일기 서버 저장소
--
-- Supabase 대시보드의 SQL Editor에 통째로 붙여넣고 한 번 실행하면 된다.
--
-- 여기에는 점수와 태그와 그날의 간지만 올라간다. 일기 본문은 올리지 않는다.
-- 새어 나갔을 때 누구의 무슨 일인지 드러나는 것은 본문뿐인데, 분석에 필요한 것은
-- 본문이 아니기 때문이다. 본문은 쓴 기기에 남고, 옮길 일이 있으면 내보내기 파일로 옮긴다.
--
-- 생년월일시도 올리지 않는다. 새 기기에서 한 번 다시 넣는 수고를 아끼자고
-- 개인을 특정할 수 있는 값을 서버에 둘 이유가 약하다.

create table if not exists public.records (
  user_id     uuid        not null references auth.users(id) on delete cascade,
  date        date        not null,
  score       smallint    not null,
  areas       text[]      not null default '{}',   -- 십성 영역 태그
  iljin       text,                                -- 그날 일진. 예: 갑신
  gan_ohaeng  text,
  ji_ohaeng   text,
  sip_gan     text,                                -- 일간에서 본 십성
  sip_ji      text,
  predicted   smallint,                            -- 그날 앱이 매긴 점수
  weekday     smallint,                            -- 요일 편향을 상쇄할 때 쓴다
  retro       boolean     not null default false,  -- 지난 날을 소급해 적은 것인지
  certainty   text,                                -- 소급일 때 날짜가 얼마나 확실한지
  updated_at  timestamptz not null default now(),
  primary key (user_id, date)
);

-- 행 수준 보안(RLS).
--
-- 이 앱에서 데이터를 지키는 것은 키가 아니라 아래 네 줄이다. anon 키는 브라우저에
-- 그대로 실려 나가는 공개 값이라 누구나 볼 수 있고, 그것만으로는 아무것도 못 하게
-- 막는 것이 RLS다. 이 부분을 빠뜨리면 키를 주운 누구나 남의 기록을 통째로 읽는다.
alter table public.records enable row level security;

drop policy if exists "본인 기록만 읽는다" on public.records;
drop policy if exists "본인 기록만 넣는다" on public.records;
drop policy if exists "본인 기록만 고친다" on public.records;
drop policy if exists "본인 기록만 지운다" on public.records;

create policy "본인 기록만 읽는다" on public.records
  for select using (auth.uid() = user_id);

create policy "본인 기록만 넣는다" on public.records
  for insert with check (auth.uid() = user_id);

create policy "본인 기록만 고친다" on public.records
  for update using (auth.uid() = user_id) with check (auth.uid() = user_id);

create policy "본인 기록만 지운다" on public.records
  for delete using (auth.uid() = user_id);

-- 제대로 걸렸는지 확인한다. rowsecurity가 true여야 한다.
-- select tablename, rowsecurity from pg_tables where tablename = 'records';
