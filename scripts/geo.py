"""서울 인허가 자료의 X·Y 좌표를 위도·경도로 바꾼다.

원본(LOCALDATA)은 가게마다 X·Y를 준다. 값이 191152.43 / 438865.16 꼴인데
이것은 위경도가 아니라 '중부원점 TM'이라는 평면 좌표다. 원점을 북위 38도,
동경 127도에 두고 그로부터 몇 미터 떨어졌는지를 적는 방식이다.
(동쪽으로 20만, 북쪽으로 50만을 더해 두어 서울은 X가 19~21만, Y가 44~46만이 된다.)

이걸 위경도로 되돌려야 지하철역 좌표와 견줄 수 있다. 역 좌표는 네이버에서
위경도로 받아 오기 때문이다.

주의 — 같은 중부원점이라도 지구를 어떤 타원으로 보느냐(측지계)에 따라
결과가 300~400m 어긋난다. GRS80(EPSG:5181)과 베셀(EPSG:2097) 두 갈래가 있고,
어느 쪽인지는 문서만 봐서는 확실치 않다. 그래서 collect.py가 네이버에서 받아 둔
실제 위경도와 견주어 얼마나 어긋나는지 로그에 찍는다. 어긋남이 크면 여기
DATUM을 바꾸면 된다.
"""

import math

# 중부원점 — 두 갈래가 원점과 가산값은 같고 타원체만 다르다.
LAT0 = math.radians(38.0)
LON0 = math.radians(127.0)
K0 = 1.0
FALSE_E = 200000.0
FALSE_N = 500000.0

ELLIPSOIDS = {
    # EPSG:5181 — GRS80. 위경도가 WGS84와 거의 같아 따로 옮길 일이 없다.
    "grs80": (6378137.0, 1 / 298.257222101),
    # EPSG:2097 — 베셀(도쿄 측지계). 이쪽은 위경도로 바꾼 뒤 한 번 더 옮겨야 한다.
    "bessel": (6377397.155, 1 / 299.1528128),
}

# 2026-09-10 첫 실측에서 GRS80으로 풀었더니 네이버가 준 실제 위경도와
# 가운데값 312m(274~319m) 어긋났다. 한쪽으로 고르게 쏠린 것이라 공식이 아니라
# 측지계가 다른 것이다. 타원체만 놓고 보면 두 갈래 차이는 7m뿐이므로,
# 312m는 도쿄 측지계를 WGS84로 옮기지 않아 생긴 값이다.
DATUM = "bessel"

# 도쿄 측지계 → WGS84 옮김값(미터). 한국에서 널리 쓰는 값이다.
TOKYO_TO_WGS84 = (-146.43, 507.89, 681.46)

# 그러고도 남는 쏠림(미터). (북쪽, 동쪽) 차례로 우리 값에 더한다.
#
# 2026-09-10 두 번째 실측: 네이버가 준 실제 위경도와 15곳을 견주니 가운데값
# 259m이 남았고, 방향이 북 +5m · 동 +258m으로 거의 정동 한 쪽이었다.
# 폭도 251~272m로 좁아, 곳마다 다른 것이 아니라 통째로 밀린 것이다.
# 원본이 표준 중부원점이 아니라 보정 원점을 쓰는 것으로 보이는데, 어느
# 쪽이든 잰 만큼 되밀면 맞는다. 다음 수집이 이 값을 다시 재어 확인해 준다.
RESIDUAL_NORTH_M = 5.0
RESIDUAL_EAST_M = 258.0


def _params(datum):
    a, f = ELLIPSOIDS[datum]
    e2 = f * (2 - f)
    return a, e2


def _meridional_arc(lat, a, e2):
    """적도에서 그 위도까지 자오선을 따라 잰 길이."""
    e4 = e2 * e2
    e6 = e4 * e2
    return a * (
        (1 - e2 / 4 - 3 * e4 / 64 - 5 * e6 / 256) * lat
        - (3 * e2 / 8 + 3 * e4 / 32 + 45 * e6 / 1024) * math.sin(2 * lat)
        + (15 * e4 / 256 + 45 * e6 / 1024) * math.sin(4 * lat)
        - (35 * e6 / 3072) * math.sin(6 * lat)
    )


def molodensky(lat_deg, lon_deg, from_datum="bessel", to_datum="grs80"):
    """측지계를 옮긴다. 베셀(도쿄)로 잰 위경도를 WGS84 위경도로 바꾼다.

    같은 땅이라도 어느 타원체를 지구라고 보고 쟀느냐에 따라 위경도가 달라진다.
    한국에서 그 차이는 300~400m쯤이라, 안 옮기면 가장 가까운 역이 뒤바뀐다.
    """
    a, e2 = _params(from_datum)
    a2, e2b = _params(to_datum)
    f = 1 - math.sqrt(1 - e2)
    f2 = 1 - math.sqrt(1 - e2b)
    da = a2 - a
    df = f2 - f
    dx, dy, dz = TOKYO_TO_WGS84

    lat = math.radians(lat_deg)
    lon = math.radians(lon_deg)
    sin_lat, cos_lat = math.sin(lat), math.cos(lat)
    sin_lon, cos_lon = math.sin(lon), math.cos(lon)
    b_over_a = 1 - f

    w = math.sqrt(1 - e2 * sin_lat ** 2)
    rm = a * (1 - e2) / w ** 3            # 자오선 곡률반지름
    rn = a / w                            # 묘유선 곡률반지름

    dlat = (
        -dx * sin_lat * cos_lon
        - dy * sin_lat * sin_lon
        + dz * cos_lat
        + da * (rn * e2 * sin_lat * cos_lat) / a
        + df * (rm / b_over_a + rn * b_over_a) * sin_lat * cos_lat
    ) / rm
    dlon = (-dx * sin_lon + dy * cos_lon) / (rn * cos_lat)

    return math.degrees(lat + dlat), math.degrees(lon + dlon)


def to_wgs84(x, y, datum=None):
    """중부원점 TM(x, y) → (위도, 경도). 못 바꾸면 None."""
    datum = datum or DATUM
    try:
        x = float(x)
        y = float(y)
    except (TypeError, ValueError):
        return None
    # 서울 안이라면 X는 대략 18~22만, Y는 43~47만이다. 벗어나면 값이 이상한 것이다.
    if not (150000 <= x <= 250000 and 400000 <= y <= 520000):
        return None

    a, e2 = _params(datum)
    ep2 = e2 / (1 - e2)

    m = _meridional_arc(LAT0, a, e2) + (y - FALSE_N) / K0
    mu = m / (a * (1 - e2 / 4 - 3 * e2 ** 2 / 64 - 5 * e2 ** 3 / 256))
    e1 = (1 - math.sqrt(1 - e2)) / (1 + math.sqrt(1 - e2))

    phi = (
        mu
        + (3 * e1 / 2 - 27 * e1 ** 3 / 32) * math.sin(2 * mu)
        + (21 * e1 ** 2 / 16 - 55 * e1 ** 4 / 32) * math.sin(4 * mu)
        + (151 * e1 ** 3 / 96) * math.sin(6 * mu)
        + (1097 * e1 ** 4 / 512) * math.sin(8 * mu)
    )

    sin_phi = math.sin(phi)
    cos_phi = math.cos(phi)
    tan_phi = math.tan(phi)

    c1 = ep2 * cos_phi ** 2
    t1 = tan_phi ** 2
    n1 = a / math.sqrt(1 - e2 * sin_phi ** 2)
    r1 = a * (1 - e2) / (1 - e2 * sin_phi ** 2) ** 1.5
    d = (x - FALSE_E) / (n1 * K0)

    lat = phi - (n1 * tan_phi / r1) * (
        d ** 2 / 2
        - (5 + 3 * t1 + 10 * c1 - 4 * c1 ** 2 - 9 * ep2) * d ** 4 / 24
        + (61 + 90 * t1 + 298 * c1 + 45 * t1 ** 2 - 252 * ep2 - 3 * c1 ** 2) * d ** 6 / 720
    )
    lon = LON0 + (
        d
        - (1 + 2 * t1 + c1) * d ** 3 / 6
        + (5 - 2 * c1 + 28 * t1 - 3 * c1 ** 2 + 8 * ep2 + 24 * t1 ** 2) * d ** 5 / 120
    ) / cos_phi

    lat_deg, lon_deg = math.degrees(lat), math.degrees(lon)
    # 베셀(도쿄)로 잰 값이면 WGS84로 한 번 더 옮긴다. 이걸 빼먹어 312m 어긋났다.
    if datum == "bessel":
        lat_deg, lon_deg = molodensky(lat_deg, lon_deg, "bessel", "grs80")
    # 그러고도 남는 쏠림을 되민다. 미터를 도로 바꿔 더한다.
    if RESIDUAL_NORTH_M or RESIDUAL_EAST_M:
        lat_deg += RESIDUAL_NORTH_M / 110574.0
        lon_deg += RESIDUAL_EAST_M / (111320.0 * math.cos(math.radians(lat_deg)))
    return round(lat_deg, 6), round(lon_deg, 6)


def to_tm(lat_deg, lon_deg, datum=None):
    """위경도 → 중부원점 TM. 되돌려 재보는 데에만 쓴다."""
    datum = datum or DATUM
    a, e2 = _params(datum)
    ep2 = e2 / (1 - e2)
    lat = math.radians(lat_deg)
    lon = math.radians(lon_deg)

    sin_phi = math.sin(lat)
    cos_phi = math.cos(lat)
    tan_phi = math.tan(lat)

    n = a / math.sqrt(1 - e2 * sin_phi ** 2)
    t = tan_phi ** 2
    c = ep2 * cos_phi ** 2
    aa = (lon - LON0) * cos_phi
    m = _meridional_arc(lat, a, e2)
    m0 = _meridional_arc(LAT0, a, e2)

    x = FALSE_E + K0 * n * (
        aa
        + (1 - t + c) * aa ** 3 / 6
        + (5 - 18 * t + t ** 2 + 72 * c - 58 * ep2) * aa ** 5 / 120
    )
    y = FALSE_N + K0 * (
        m - m0
        + n * tan_phi * (
            aa ** 2 / 2
            + (5 - t + 9 * c + 4 * c ** 2) * aa ** 4 / 24
            + (61 - 58 * t + t ** 2 + 600 * c - 330 * ep2) * aa ** 6 / 720
        )
    )
    return x, y


def metres_between(a, b):
    """두 위경도 사이 거리(m). 서울 안에서는 이 어림으로 충분하다."""
    lat1, lon1 = a
    lat2, lon2 = b
    mid = math.radians((lat1 + lat2) / 2)
    dx = (lon2 - lon1) * 111320 * math.cos(mid)
    dy = (lat2 - lat1) * 110574
    return math.hypot(dx, dy)


if __name__ == "__main__":
    # 되돌려 재보기 — 위경도를 TM으로 보냈다가 다시 가져와 얼마나 어긋나는지.
    # 이것이 맞는다고 측지계까지 맞는 것은 아니다. 공식이 맞는지만 본다.
    print("되돌려 재보기 (공식이 맞는지만 봅니다)")
    for name, lat, lon in [
        ("서울시청 언저리", 37.5663, 126.9779),
        ("합정 언저리", 37.5495, 126.9137),
        ("강남 언저리", 37.4979, 127.0276),
        ("원점", 38.0, 127.0),
    ]:
        for datum in ("grs80", "bessel"):
            x, y = to_tm(lat, lon, datum)
            back = to_wgs84(x, y, datum)
            off = metres_between((lat, lon), back) if back else float("nan")
            print(f"  {name:<12} {datum:<7} X={x:10.2f} Y={y:10.2f}  되돌린 오차 {off:.4f}m")

    print()
    print("같은 X·Y를 두 측지계로 풀면 얼마나 갈리나")
    x, y = 191152.432649234, 438865.160717275     # 원본 표본: 금천구 시흥동 992-47
    a = to_wgs84(x, y, "grs80")
    b = to_wgs84(x, y, "bessel")
    print(f"  grs80  {a}")
    print(f"  bessel {b}")
    print(f"  두 값의 거리 {metres_between(a, b):,.0f}m")
