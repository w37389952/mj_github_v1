// 아래 두 줄만 채우면 로그인과 동기화가 켜진다.
// 비워 두면 앱은 지금처럼 브라우저 안에서만 돌아간다. 그래도 다 쓸 수 있다.
//
// 값은 Supabase 대시보드 > Project Settings > API 에서 가져온다.
//   SUPABASE_URL       Project URL
//   SUPABASE_ANON_KEY  anon public 키
//
// anon 키는 브라우저에 그대로 실려 나가는 공개 값이라 여기 적어도 된다.
// 데이터를 지키는 것은 이 키가 아니라 supabase.sql의 행 수준 보안(RLS)이다.
// service_role 키는 절대 여기 적지 말 것. 그것은 모든 잠금을 지나친다.

window.ILJIN_CONFIG = {
  SUPABASE_URL: "https://yvlpooppbsolmsinfjmo.supabase.co",
  SUPABASE_ANON_KEY:
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inl2bHBvb3BwYnNvbG1zaW5mam1vIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODkwMzc4NTUsImV4cCI6MjEwNDYxMzg1NX0.Wn3uEcJ5AaQsMiaWtwCP8eEHqpyemF1GWDGCCGKBONg",
};
