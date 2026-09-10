// 만세력 — 양력 날짜와 시각을 사주 네 기둥으로 옮긴다.
//
// 이 파일에는 인터넷도 서버도 필요 없다. 일진은 60갑자가 끊김 없이 도는 것이라
// 기준일 하루만 맞으면 나머지는 나눗셈으로 나오고, 절기는 태양의 위치를 직접
// 계산해서 얻는다. 따라서 앱은 비행기 안에서도 2200년 일진을 뽑을 수 있다.

const GAN = ["갑","을","병","정","무","기","경","신","임","계"];
const JI  = ["자","축","인","묘","진","사","오","미","신","유","술","해"];

// 천간과 지지에 붙는 오행. 일진 점수는 결국 이 다섯 글자의 관계로 매겨진다.
const GAN_OHAENG = ["목","목","화","화","토","토","금","금","수","수"];
const JI_OHAENG   = ["수","토","목","목","토","화","화","토","금","금","토","수"];

// 음양. 같은 목(木)이라도 갑목과 을목은 성질이 다르므로 함께 들고 다닌다.
const GAN_EUMYANG = ["양","음","양","음","양","음","양","음","양","음"];

const DEG = Math.PI / 180;

// ── 율리우스일 ──────────────────────────────────────────────

// 양력 날짜를 율리우스일 번호로 옮긴다. 날짜 사이의 간격을 빼기 한 번으로
// 구할 수 있게 되므로, 60갑자를 돌리는 계산이 여기서 시작된다.
function toJDN(y, m, d) {
  const a = Math.floor((14 - m) / 12);
  const yy = y + 4800 - a;
  const mm = m + 12 * a - 3;
  return d + Math.floor((153 * mm + 2) / 5) + 365 * yy
           + Math.floor(yy / 4) - Math.floor(yy / 100) + Math.floor(yy / 400) - 32045;
}

// 절기 계산은 하루보다 잔 단위가 필요하므로 시각까지 담은 율리우스일을 쓴다.
// 한국 표준시(UTC+9)로 받아 세계시로 되돌린다.
function toJD(y, m, d, hour = 0, minute = 0) {
  return toJDN(y, m, d) - 0.5 + (hour - 9 + minute / 60) / 24;
}

// ── 태양의 겉보기 황경 ───────────────────────────────────────

// 절기란 태양이 황도 위 특정 각도를 지나는 순간이다. 입춘은 315도,
// 경칩은 345도… 이런 식으로 30도마다 하나씩 놓인다.
// 오차는 1분 남짓이라 절기가 자정에 아주 가까이 걸린 해에는 하루가 어긋날 수
// 있다. 그런 날은 KASI 발표값으로 덮어쓸 수 있게 예외 표를 따로 둔다.
function solarLongitude(jd) {
  const T = (jd - 2451545.0) / 36525;

  const L0 = 280.46646 + 36000.76983 * T + 0.0003032 * T * T;
  const M  = 357.52911 + 35999.05029 * T - 0.0001537 * T * T;

  // 지구 궤도가 타원이라 태양은 고르게 움직이지 않는다. 그 어긋남을 보정한다.
  const C = (1.914602 - 0.004817 * T - 0.000014 * T * T) * Math.sin(M * DEG)
          + (0.019993 - 0.000101 * T) * Math.sin(2 * M * DEG)
          + 0.000289 * Math.sin(3 * M * DEG);

  // 달이 지구 자전축을 흔드는 만큼(장동)과 빛이 오는 데 걸리는 시간을 뺀다.
  const omega = 125.04 - 1934.136 * T;
  const apparent = L0 + C - 0.00569 - 0.00478 * Math.sin(omega * DEG);

  return ((apparent % 360) + 360) % 360;
}

// 태양 황경이 목표 각도에 닿는 순간을 이분법으로 좁힌다.
// 황경은 1년에 한 바퀴만 돌아 단조롭게 늘어나므로 이분법이 반드시 수렴한다.
function solarTermJD(targetDeg, guessJD) {
  const norm = (deg) => ((deg - targetDeg) % 360 + 540) % 360 - 180;  // -180~180

  let lo = guessJD - 20, hi = guessJD + 20;
  for (let i = 0; i < 60; i++) {
    const mid = (lo + hi) / 2;
    if (norm(solarLongitude(mid)) < 0) lo = mid; else hi = mid;
  }
  return (lo + hi) / 2;
}

// 그 해의 절기 24개 가운데 월을 가르는 12개(절)를 순서대로 돌려준다.
// 중기(우수·춘분 같은 것)는 월을 가르지 않으므로 여기 들어오지 않는다.
function majorTerms(year) {
  const terms = [];
  for (let k = 0; k < 12; k++) {
    const deg = (315 + 30 * k) % 360;         // 입춘 315도에서 시작한다
    // 입춘은 2월 초, 그다음부터 한 달에 하나씩 뒤로 간다.
    const guess = toJD(year, 1, 1) + 34 + k * 30.44;
    terms.push({ deg, jd: solarTermJD(deg, guess) });
  }
  return terms;
}

// ── 네 기둥 ────────────────────────────────────────────────

// 일주. 60갑자가 하루도 빠짐없이 돌기 때문에 나머지 연산 하나로 끝난다.
// 여기가 이 앱의 뿌리라 다른 어떤 계산보다 먼저 맞아야 한다.
function dayPillar(jdn) {
  return { gan: (jdn + 9) % 10, ji: (jdn + 1) % 12 };
}

// 연주. 사주의 한 해는 1월 1일이 아니라 입춘에 바뀐다.
// 그래서 2월 초에 태어난 사람은 띠가 앞 해로 넘어가는 일이 흔하다.
function yearPillar(y, m, d, hour, minute, terms) {
  const jd = toJD(y, m, d, hour, minute);
  const sajuYear = jd < terms[0].jd ? y - 1 : y;   // terms[0]이 그 해 입춘이다
  return { gan: (sajuYear - 4 + 60) % 10, ji: (sajuYear - 4 + 60) % 12, year: sajuYear };
}

// 월주. 달의 경계도 1일이 아니라 절기다. 지지는 절기가 곧바로 정하고,
// 천간은 연간에서 끌어온다(오호둔). 갑·기년은 병인월로 시작하는 식이다.
//
// 절기는 해를 걸쳐 이어지므로 앞 해 것까지 붙여 놓고 찾는다. 1월생은
// 아직 입춘 전이라 앞 해 절기 구간에 속하기 때문이다.
function monthPillar(jd, yearGan, y) {
  const all = [...majorTerms(y - 1), ...majorTerms(y)];
  let idx = all.length - 1;
  while (idx >= 0 && jd < all[idx].jd) idx--;

  const seq = ((idx % 12) + 12) % 12;               // 입춘을 0으로 둔 순번
  const ji = (2 + seq) % 12;                        // 입춘 다음은 인(寅)월이다
  const gan = ((yearGan % 5) * 2 + 2 + seq) % 10;   // 오호둔
  return { gan, ji };
}

// 시주. 자시는 밤 11시에 열려 하루를 걸치므로 12시간이 아니라 23시부터 센다.
// 천간은 일간에서 끌어온다(오서둔). 갑·기일은 갑자시로 시작한다.
function hourPillar(hour, minute, dayGan) {
  const t = hour * 60 + minute;
  const ji = Math.floor(((t + 60) % 1440) / 120);   // 23:00~00:59가 자시다
  const gan = ((dayGan % 5) * 2 + ji) % 10;         // 오서둔
  return { gan, ji };
}

// 표준시는 동경 135도를 기준으로 하는데 한국은 그보다 서쪽에 있어
// 시계가 해보다 30분쯤 빠르다. 시주 경계에 걸린 사람은 이 보정으로 기둥이 바뀐다.
function trueSolarMinutes(hour, minute, longitude = 126.978) {
  return hour * 60 + minute + (longitude - 135) * 4;
}

// ── 바깥으로 내보내는 하나의 입구 ──────────────────────────

// 생년월일시로 원국 네 기둥을, 날짜만으로 그날 일진을 얻는다.
//
// 태어난 시각을 모르는 사람이 많다. 그럴 때는 시주를 비운 세 기둥으로 본다.
// 연·월·일은 그대로 나오고 강약만 여섯 글자로 재게 되므로, 일진 분석에는
// 지장이 없다. 시주가 필요한 것은 원국뿐이고 일진은 날짜만으로 정해지기 때문이다.
function saju(y, m, d, hour = 12, minute = 0, opts = {}) {
  const useTrueSolar = opts.trueSolar !== false;      // 진태양시 보정은 기본으로 켠다
  const longitude = opts.longitude ?? 126.978;        // 서울
  const 시모름 = opts.시모름 === true;

  let hh = hour, mm = minute;
  if (useTrueSolar) {
    const t = trueSolarMinutes(hour, minute, longitude);
    hh = Math.floor(((t % 1440) + 1440) % 1440 / 60);
    mm = Math.round(((t % 1440) + 1440) % 1440 % 60);
  }

  const jdn = toJDN(y, m, d);
  const jd = toJD(y, m, d, hh, mm);

  const terms = majorTerms(y);
  const day = dayPillar(jdn);
  const year = yearPillar(y, m, d, hh, mm, terms);
  const month = monthPillar(jd, year.gan, y);
  let time = 시모름 ? null : hourPillar(hh, mm, day.gan);

  // 쌍둥이 둘째는 시주를 다음 간지로 민다. 임진시로 태어났다면 계사시로 본다.
  // 유파가 갈리는 자리이므로 설정을 끄면 첫째와 같은 시주로 돌아간다.
  // 어느 쪽이 맞는지는 쌍둥이 둘의 기록을 견주어 보면 알 수 있다.
  if (time && opts.쌍둥이둘째) {
    time = { gan: (time.gan + 1) % 10, ji: (time.ji + 1) % 12 };
  }

  const name = (p) => (p ? GAN[p.gan] + JI[p.ji] : null);
  return {
    연주: name(year), 월주: name(month), 일주: name(day), 시주: name(time),
    시모름,
    쌍둥이둘째: opts.쌍둥이둘째 === true && !시모름,
    일간: GAN[day.gan],
    일간오행: GAN_OHAENG[day.gan],
    일간음양: GAN_EUMYANG[day.gan],
    사주연도: year.year,
    // 대운은 태어난 순간이 절기에서 얼마나 떨어져 있는지로 시작 나이를 정하므로
    // 입력값과 율리우스일을 함께 들려 보낸다.
    입력: { y, m, d, hour, minute },
    jd,
    raw: { year, month, day, time },
  };
}

// 오늘 일진만 필요할 때 쓰는 가벼운 입구. 위젯이 부르는 것이 이것이다.
function iljin(y, m, d) {
  const p = dayPillar(toJDN(y, m, d));
  return {
    이름: GAN[p.gan] + JI[p.ji],
    천간오행: GAN_OHAENG[p.gan],
    지지오행: JI_OHAENG[p.ji],
    음양: GAN_EUMYANG[p.gan],
  };
}

// ── 십성 ──────────────────────────────────────────────────

// 지지 속에도 천간이 들어 있다. 그중 그 지지를 대표하는 것이 본기(本氣)이고,
// 십성은 이 본기로 따진다.
const JI_BONGI = [8, 5, 0, 1, 4, 2, 3, 5, 6, 7, 4, 8];   // 자=계, 축=기, 인=갑 …

// 십성은 일간과의 관계다. 오행이 어느 쪽으로 흐르는지(생·극)와
// 음양이 같은지 다른지, 이 둘만으로 열 개가 모두 갈린다.
function sipseong(dayGan, targetGan) {
  const 나 = GAN_OHAENG[dayGan], 상대 = GAN_OHAENG[targetGan];
  const 같은음양 = GAN_EUMYANG[dayGan] === GAN_EUMYANG[targetGan];

  const 생하는곳 = { 목:"화", 화:"토", 토:"금", 금:"수", 수:"목" };
  const 극하는곳 = { 목:"토", 화:"금", 토:"수", 금:"목", 수:"화" };

  if (상대 === 나)            return 같은음양 ? "비견" : "겁재";
  if (생하는곳[나] === 상대)   return 같은음양 ? "식신" : "상관";
  if (극하는곳[나] === 상대)   return 같은음양 ? "편재" : "정재";
  if (극하는곳[상대] === 나)   return 같은음양 ? "편관" : "정관";
  return 같은음양 ? "편인" : "정인";
}

// 십성은 저마다 삶의 한 영역을 가리킨다. 기록을 이 영역으로 받아 두면
// 사건과 그날의 기운을 같은 말로 견줄 수 있게 된다.
const SIPSEONG_영역 = {
  비견: "동료·경쟁", 겁재: "동료·경쟁",
  식신: "표현·창작", 상관: "표현·창작",
  편재: "돈·거래",   정재: "돈·거래",
  편관: "직장·윗사람", 정관: "직장·윗사람",
  편인: "공부·문서", 정인: "공부·문서",
};

const sipseongOf = (dayGan, p) => ({
  천간: sipseong(dayGan, p.gan),
  지지: sipseong(dayGan, JI_BONGI[p.ji]),
});

// ── 대운 ──────────────────────────────────────────────────

// 대운은 월주에서 출발해 열 해에 한 칸씩 옮겨 간다. 어느 쪽으로 가는지는
// 태어난 해의 음양과 성별이 정한다. 양남·음녀는 순행, 음남·양녀는 역행이다.
// 시작 나이는 태어난 날에서 절기까지의 거리를 사흘에 한 해로 세어 얻는다.
function daeun(birth, gender, count = 9) {
  const { year, month } = birth.raw;
  const 양년 = GAN_EUMYANG[year.gan] === "양";
  const 순행 = (양년 && gender === "남") || (!양년 && gender === "여");

  // 생일이 낀 절기 구간의 양 끝을 찾는다.
  const y = birth.입력.y;
  const all = [...majorTerms(y - 1), ...majorTerms(y), ...majorTerms(y + 1)];
  let i = all.length - 1;
  while (i >= 0 && birth.jd < all[i].jd) i--;

  const 거리 = 순행 ? all[i + 1].jd - birth.jd : birth.jd - all[i].jd;
  const 대운수 = Math.max(1, Math.round(거리 / 3));

  const list = [];
  for (let k = 1; k <= count; k++) {
    const step = 순행 ? k : -k;
    const gan = ((month.gan + step) % 10 + 10) % 10;
    const ji  = ((month.ji  + step) % 12 + 12) % 12;
    list.push({
      나이: 대운수 + (k - 1) * 10,
      이름: GAN[gan] + JI[ji],
      십성: sipseongOf(birth.raw.day.gan, { gan, ji }),
    });
  }
  return { 순행, 대운수, 목록: list };
}

// ── 강약과 용신 ──────────────────────────────────────────

const 생하는곳 = { 목:"화", 화:"토", 토:"금", 금:"수", 수:"목" };
const 극하는곳 = { 목:"토", 화:"금", 토:"수", 금:"목", 수:"화" };
const 생받는곳 = { 화:"목", 토:"화", 금:"토", 수:"금", 목:"수" };   // 나를 생하는 오행(인성)
const 극받는곳 = { 화:"수", 토:"목", 금:"화", 수:"토", 목:"금" };   // 나를 극하는 오행(관성)

// 일간의 강약. 월지가 가장 무겁고 일지가 그다음이다. 월지는 계절 그 자체라
// 나머지 여섯 글자를 합친 것만큼의 힘을 가진다고 본다.
//
// 득령·득지·득세는 명리에서 강약을 가르는 세 가지 잣대다.
//   득령 — 월지가 나를 돕는가
//   득지 — 일지가 나를 돕는가
//   득세 — 나머지 글자 가운데 나를 돕는 것이 셋 이상인가
function strength(원국) {
  const dg = 원국.raw.day.gan;
  const 나 = GAN_OHAENG[dg];
  const 돕는가 = (o) => o === 나 || 생받는곳[나] === o;   // 비겁이거나 인성이면 돕는다

  const { year, month, day, time } = 원국.raw;
  const 월지 = JI_OHAENG[month.ji];
  const 일지 = JI_OHAENG[day.ji];

  // 시각을 모르면 시간·시지 두 글자가 없다. 만점을 함께 줄여야
  // 같은 잣대로 강약을 견줄 수 있다.
  const 나머지 = [
    GAN_OHAENG[year.gan], GAN_OHAENG[month.gan], JI_OHAENG[year.ji],
    ...(time ? [GAN_OHAENG[time.gan], JI_OHAENG[time.ji]] : []),
  ];

  const 득령 = 돕는가(월지), 득지 = 돕는가(일지);
  const 우군 = 나머지.filter(돕는가).length;
  const 득세 = 우군 + (득령 ? 1 : 0) + (득지 ? 1 : 0) >= 3;

  // 월지 3, 일지 2, 나머지 각 1. 만점의 절반을 넘으면 신강으로 본다.
  const 만점 = 5 + 나머지.length;
  const 점 = (득령 ? 3 : 0) + (득지 ? 2 : 0) + 우군;
  return { 득령, 득지, 득세, 점, 만점, 신강: 점 >= 만점 / 2, 일간오행: 나, 시모름: !time };
}

// 월지가 어느 계절인지. 조후는 결국 사주가 찬지 더운지를 묻는 것이다.
const 계절 = (ji) =>
  [2,3,4].includes(ji) ? "봄" : [5,6,7].includes(ji) ? "여름" :
  [8,9,10].includes(ji) ? "가을" : "겨울";

// 용신 후보. 억부와 조후는 서로 다른 물음에서 나오므로 답이 갈릴 수 있다.
// 그 갈림을 감추지 않고 후보로 나란히 세워 둔다. 어느 쪽이 맞는지는
// 나중에 쌓인 기록이 정한다.
function yongsin(원국) {
  const s = strength(원국);
  const 나 = s.일간오행;

  // 억부 — 넘치면 덜어내고 모자라면 채운다. 사주의 일곱쯤이 이 방식으로 풀린다.
  //
  // 신강이면 기운을 빼는 쪽(식상·재성)이 용신이고 더 보태는 쪽(비겁·인성)이 기신이다.
  // 신약이면 정반대로, 채워 주는 쪽(인성·비겁)이 용신이고
  // 나를 극하는 관성과 기운을 빼는 식상이 함께 부담이 된다.
  const 억부 = s.신강
    ? {
        용신: [생하는곳[나], 극하는곳[나]],
        기신: [나, 생받는곳[나]],
        까닭: `일간이 ${s.점}/${s.만점}으로 강하다. 덜어내는 쪽이 반갑다.`,
      }
    : {
        용신: [생받는곳[나], 나],
        기신: [극받는곳[나], 생하는곳[나]],
        까닭: `일간이 ${s.점}/${s.만점}으로 약하다. 채워 주는 쪽이 반갑다.`,
      };

  // 조후 — 한난조습을 본다. 겨울에 난 사주는 불이, 여름에 난 사주는 물이 아쉽다.
  const 절 = 계절(원국.raw.month.ji);
  const 조후 = 절 === "겨울"
    ? { 용신: ["화", "목"], 기신: ["수", "금"], 까닭: `${절}에 났다. 사주가 차서 불이 아쉽다.` }
    : 절 === "여름"
    ? { 용신: ["수", "금"], 기신: ["화", "토"], 까닭: `${절}에 났다. 사주가 더워서 물이 아쉽다.` }
    : { 용신: [], 기신: [], 까닭: `${절}에 났다. 춥지도 덥지도 않아 조후가 급하지 않다.` };

  // 두 후보가 같은 답을 내면 용신 논쟁이 거의 없는 사주다.
  const 일치 = 조후.용신.length > 0 &&
    조후.용신.some((o) => 억부.용신.includes(o));

  return { 강약: s, 계절: 절, 억부, 조후, 일치, 기본: 억부 };
}

// ── 어느 날의 네 겹 운 ────────────────────────────────────

// 하루의 기운은 일진 하나로 정해지지 않는다. 대운이 큰 바탕을 깔고,
// 세운과 월운이 그 위에 얹히고, 일진이 마지막에 색을 입힌다.
// 넷을 같이 봐야 같은 갑신일이라도 해마다 다르게 읽힌다.
function fortune(birth, gender, y, m, d) {
  const 그날 = saju(y, m, d, 12, 0);
  const 대 = daeun(birth, gender);
  const 만나이 = y - birth.입력.y - (m < birth.입력.m || (m === birth.입력.m && d < birth.입력.d) ? 1 : 0);

  let 현재대운 = 대.목록[0];
  for (const x of 대.목록) if (만나이 >= x.나이) 현재대운 = x;

  const dg = birth.raw.day.gan;
  const 겹 = (p) => ({ 이름: GAN[p.gan] + JI[p.ji], 십성: sipseongOf(dg, p) });

  return {
    만나이,
    대운: { ...현재대운, 남은해: 현재대운.나이 + 10 - 만나이 },
    세운: 겹(그날.raw.year),
    월운: 겹(그날.raw.month),
    일운: 겹(그날.raw.day),
  };
}

if (typeof window !== "undefined") {
  window.Manse = {
    saju, iljin, dayPillar, toJDN, majorTerms, solarLongitude,
    sipseong, sipseongOf, daeun, fortune, strength, yongsin,
    GAN, JI, GAN_OHAENG, JI_OHAENG, GAN_EUMYANG, JI_BONGI, SIPSEONG_영역,
  };
}
