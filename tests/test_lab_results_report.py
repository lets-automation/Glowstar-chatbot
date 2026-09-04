"""
The lab report must reproduce the CLIENT'S ERP, figure for figure.

Verified 2026-08-24 against a screenshot of their ERP for May 2026. If any of
these numbers move, either the definition drifted or the database changed -
both are things we must find out from a test, not from the client in a meeting.
"""
import pytest

from app.agent.reports import lab_results_report

pytestmark = pytest.mark.integration

# Kapan -> (PNo, PWt, PLSAmt, GIAAmt), straight off the client's ERP screenshot.
ERP_MAY_2026 = {
    "MZ26": (1, 0.500, 10.0600, 6.5200),      "NA26": (1, 0.710, 68.2300, 44.6000),
    "NB26": (3, 4.140, 665.7800, 742.5300),   "NE26": (7, 2.710, 87.9000, 82.7600),
    "NF26": (78, 39.965, 1634.1600, 1649.5300), "NH26": (8, 1.470, 36.6700, 36.6700),
    "NI26": (58, 14.930, 404.9200, 399.6500), "NK26": (31, 14.800, 535.3100, 527.9200),
    "NL26": (317, 122.510, 4588.1900, 4725.9000), "NO26": (224, 138.160, 9345.4800, 9693.6900),
    "NP26": (4, 18.770, 10565.0100, 12664.3800), "NQ26": (1, 3.030, 2266.3300, 2540.2000),
    "NR26": (448, 171.665, 5403.0400, 5567.0300), "NS26": (551, 380.970, 29838.8100, 30346.6400),
    "NT26": (229, 142.390, 6895.3300, 6973.2800), "NU26": (3, 5.610, 4261.3300, 4212.0700),
    "NV26": (5, 12.620, 4288.4000, 4318.7000), "NW26": (68, 42.520, 3492.7900, 3690.8400),
    "NX26": (156, 71.010, 3571.1000, 3591.5500), "NY26": (157, 51.840, 1917.2300, 1862.8100),
    "NZ26": (145, 57.690, 2161.8300, 2171.3300), "OA26": (24, 8.070, 271.2200, 279.0800),
    "OB26": (1, 1.000, 56.3000, 57.9900), "OC26": (1, 0.900, 74.8100, 61.0300),
    "OD26": (10, 6.620, 418.8500, 472.1800), "OE26": (6, 5.810, 594.9300, 575.2300),
    "OG26": (25, 10.520, 450.5100, 439.7100),
}


@pytest.fixture(scope="module")
def report():
    r = lab_results_report("2026-05-01", "2026-06-01")
    if not r["sections"]:
        pytest.skip("database not reachable")
    return {s["title"]: s for s in r["sections"]}


def test_totals_match_the_erp(report):
    row = report["Summary"]["rows"][0]
    assert row["PNo"] == 2562
    assert row["Kapans"] == 27
    assert float(row["PWt"]) == pytest.approx(1330.930, abs=0.001)
    assert float(row["PLSAmt"]) == pytest.approx(93904.5200, abs=0.01)
    assert float(row["GIAAmt"]) == pytest.approx(97733.8200, abs=0.01)
    assert float(row["DiffAmt"]) == pytest.approx(3829.30, abs=0.01)
    assert float(row["DiffPer"]) == pytest.approx(4.08, abs=0.01)


def test_every_kapan_row_matches_the_erp(report):
    got = {r["Kapan"].strip(): r for r in report["By kapan"]["rows"]}
    assert set(got) == set(ERP_MAY_2026)
    for kapan, (pno, pwt, pls, gia) in ERP_MAY_2026.items():
        r = got[kapan]
        assert r["PNo"] == pno, kapan
        assert float(r["PWt"]) == pytest.approx(pwt, abs=0.001), kapan
        assert float(r["PLSAmt"]) == pytest.approx(pls, abs=0.01), kapan
        assert float(r["GIAAmt"]) == pytest.approx(gia, abs=0.01), kapan


def test_hrd_and_igi_are_included(report):
    # Dropping them gives 2,529 - the omission the client challenged us on.
    labs = {r["Lab"].strip(): r["PNo"] for r in report["By lab"]["rows"]}
    assert labs == {"GIA": 2529, "HRD": 31, "IGI": 2}
    assert sum(labs.values()) == 2562
