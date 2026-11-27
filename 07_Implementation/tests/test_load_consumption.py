import csv

import pytest

from src.dashboard_series import catalogue


def write_table(path, header, rows):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(header)
        writer.writerows(rows)


def indexed_fixture(tmp_path, *, failed=False, missing=False, duplicate=False, tariff=.17234567, zero=False):
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    axes = ["2021-01-01 00:00:00", "2021-01-01 00:30:00"]
    requested = {1: [0., 0.], 2: [10.123456789, 2.], 3: [4., 20.123456789],
                 4: [5., 7.], 5: [3., 9.], 9: [1., 0.]}
    if zero:
        requested = {key: [0., 0.] for key in requested}
    write_table(inputs / "bus_assignments_used.csv", ["bus_id", "category"],
                [(2, "Residential"), (2, "residential"), (3, "Residential"), (4, "Commercial"), (5, "Manufacturing")])
    items, load = [], []
    for i, axis in enumerate(axes):
        for bus, samples in requested.items():
            p = samples[i]
            shed = p * .25
            load.append((axis, bus, p, p * .2))
            if missing and bus == 3 and i == 1:
                continue
            row = (axis, bus, p, p*.2, p-shed, (p-shed)*.2, shed, shed*.2, shed*2)
            items.append(row)
            if duplicate and bus == 3 and i == 1:
                items.append(row)
    # A legacy archive with P/Q and no interval energy or embedded assignments.
    write_table(tmp_path / "buses.csv",
                ["timestamp", "bus_id", "requested_load_kw", "requested_load_kvar", "load_input_kw",
                 "load_input_kvar", "shedding_kw", "shedding_kvar", "shedding_cost"], items)
    write_table(inputs / "load_profile.csv", ["timestamp", "bus_id", "p_kw", "q_kvar"], load)
    blocks = []

    def add(value):
        blocks.append(value)
        return len(blocks) - 1

    hours = [{"timestamp": axis, "dt_hours": .5, "converged": not (i and failed)}
             for i, axis in enumerate(axes)]
    result = catalogue(tmp_path, hours, add, root=tmp_path, snapshot={"dt_hours": .5, "window": {"hours": 2}},
                       inputs_cache={}, economics={"grid_import_tariff_per_kwh": tariff})
    return result, blocks, requested


def column(group, blocks, entity, field):
    values = {}
    for _, _, ref in group["entities"][entity]:
        indices, data = blocks[ref]
        values.update(zip(indices, data.get(field, [None] * len(indices))))
    return [values.get(index) for index in range(2)]


def test_category_input_and_executed_power_energy_reconcile_and_exclude_idle_slack_from_counts(tmp_path):
    data, blocks, requested = indexed_fixture(tmp_path)
    groups = data["groups"]
    sums = [requested[2][i]+requested[3][i] for i in range(2)]
    assert column(groups["load input"], blocks, "residential", "p_kw") == sums
    assert column(groups["load output"], blocks, "residential", "load_input_kw") == pytest.approx([.75*s for s in sums])
    assert column(groups["load output"], blocks, "residential", "shedding_kvar") == pytest.approx([.05*s for s in sums])
    assert column(groups["load input"], blocks, "residential", "p_kwh") == pytest.approx([.5*s for s in sums])
    assert groups["load output"]["entity_fields"]["residential"] == groups["load output"]["fields"]
    report = blocks[data["consumption"]]
    rows = {record["id"]: record for record in report["categories"]}
    res = rows["residential"]
    assert res["requested_kwh"] == pytest.approx(.5*sum(sums))
    assert res["served_kwh"] == pytest.approx(.75*res["requested_kwh"])
    assert res["peak_kw"] == max(sums)
    assert res["peak_kw"] < sum(max(requested[bus]) for bus in [2, 3])
    assert res["tariff_estimate"] == pytest.approx(.17234567*res["served_kwh"])
    assert res["shedding_penalty"] == pytest.approx(sum(sums)*.5)
    assert rows["unclassified"]["bus_count"] == 1
    assert rows["Total"]["bus_count"] == 5
    assert {row["id"] for row in report["buses"]} == {"2", "3", "4", "5", "9"}
    assert sum(row["share_percent"] for key, row in rows.items() if key!="Total") == pytest.approx(100.)


@pytest.mark.parametrize("case", ["missing", "failed", "duplicate"])
def test_partial_or_duplicate_samples_never_create_complete_aggregates(tmp_path, case):
    data, blocks, _ = indexed_fixture(tmp_path, **{case: True})
    group = data["groups"]["load output"]
    assert column(group, blocks, "residential", "served_load_kwh")[1] is None
    report = blocks[data["consumption"]]
    res = next(row for row in report["categories"] if row["id"] == "residential")
    assert res["served_kwh"] is None and res["tariff_estimate"] is None
    if case == "failed":
        assert res["requested_kwh"] is not None
    else:
        assert res["requested_kwh"] is None and res["peak_kw"] is None


def test_zero_energy_is_recorded_and_no_tariff_or_share_is_assumed(tmp_path):
    data, blocks, _ = indexed_fixture(tmp_path, tariff=None, zero=True)
    report = blocks[data["consumption"]]
    total = next(row for row in report["categories"] if row["id"] == "Total")
    assert total["requested_kwh"] == total["served_kwh"] == total["shed_kwh"] == 0
    assert total["share_percent"] is None and total["tariff_estimate"] is None
    assert not report["buses"]
