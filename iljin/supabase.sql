-- 일진일기 서버 저장소
--
-- Supabase 대시보드의 SQL Editor에 통째로 붙여넣고 실행하면 된다. 몇 번을 다시
-- 돌려도 괜찮게 짰으므로, 이 파일이 바뀌면 전체를 다시 실행하면 된다.
--
-- 점수·태그·그날의 간지는 그대로 올라간다. 일기 본문은 기기 안에서 잠근 뒤에만
-- 올라오고, 푸는 열쇠는 서버에 없다. 새어 나갔을 때 누구의 무슨 일인지 드러나는
-- 것은 본문뿐이라, 본문만큼은 서버도 운영자도 읽을 수 없게 한다.
--
-- 생년월일시도 일기와 같은 열쇠로 잠가서만 올린다. 그대로 두면 개인을 특정할 수
-- 있는 값이지만, 잠겨 있으면 서버도 운영자도 읽지 못한다. 새 기기에서 잠금을 풀면
-- 따라오므로 기기마다 다시 넣지 않아도 된다.

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

-- 일기 본문. 기기에서 AES-GCM으로 잠근 문자열이며, 서버는 이것을 풀 수 없다.
alter table public.records add column if not exists note_cipher text;

-- 일기 잠금의 열쇠 보관함.
--
-- 글을 잠그는 데이터 열쇠는 사용자마다 하나이고, 그 열쇠를 두 번 잠가 여기 둔다.
-- 한 번은 일기 비밀번호로, 한 번은 복구 코드로. 비밀번호도 복구 코드도 서버로 오지
-- 않으므로, 여기 있는 것만으로는 어느 쪽도 풀 수 없다. 소금은 비밀이 아니다.
create table if not exists public.vault (
  user_id     uuid        primary key references auth.users(id) on delete cascade,
  salt_p      text        not null,   -- 일기 비밀번호용 소금
  wrap_p      text        not null,   -- 일기 비밀번호로 잠근 데이터 열쇠
  salt_r      text        not null,   -- 복구 코드용 소금
  wrap_r      text        not null,   -- 복구 코드로 잠근 데이터 열쇠
  updated_at  timestamptz not null default now()
);

-- 생년월일시. 일기와 같은 데이터 열쇠로 잠근 문자열이다.
alter table public.vault add column if not exists me_cipher text;

-- 행 수준 보안(RLS).
--
-- 이 앱에서 데이터를 지키는 것은 키가 아니라 아래 정책들이다. anon 키는 브라우저에
-- 그대로 실려 나가는 공개 값이라 누구나 볼 수 있고, 그것만으로는 아무것도 못 하게
-- 막는 것이 RLS다. 이 부분을 빠뜨리면 키를 주운 누구나 남의 기록을 통째로 읽는다.
alter table public.records enable row level security;
alter table public.vault   enable row level security;

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

drop policy if exists "본인 열쇠만 읽는다" on public.vault;
drop policy if exists "본인 열쇠만 넣는다" on public.vault;
drop policy if exists "본인 열쇠만 고친다" on public.vault;
drop policy if exists "본인 열쇠만 지운다" on public.vault;

create policy "본인 열쇠만 읽는다" on public.vault
  for select using (auth.uid() = user_id);
create policy "본인 열쇠만 넣는다" on public.vault
  for insert with check (auth.uid() = user_id);
create policy "본인 열쇠만 고친다" on public.vault
  for update using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "본인 열쇠만 지운다" on public.vault
  for delete using (auth.uid() = user_id);

-- 제대로 걸렸는지 확인한다. 두 표 모두 rowsecurity가 true여야 한다.
-- select tablename, rowsecurity from pg_tables where tablename in ('records', 'vault');
