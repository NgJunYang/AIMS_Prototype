import pytest

from app.assignments import parse_roster_csv


@pytest.mark.parametrize("csv", [
    "name,student_id\nAlex,A1\nBea,B2\n",
    "student_id,name\nA1,Alex\nB2,Bea\n",
    "\ufeff Student ID , Student Name \r\n A1 , Alex \r\n B2 , Bea \r\n",
    "Alex,A1\nBea,B2\n",
])
def test_roster_maps_headers_and_legacy_name_first(csv):
    assert [(r.name, r.student_id) for r in parse_roster_csv(csv.encode())] == [("Alex", "A1"), ("Bea", "B2")]


def test_roster_quotes_blank_lines_and_optional_id():
    entries = parse_roster_csv(b'\nname,student_id\n"Tan, Alex",A1\n\nBea\n')
    assert [(r.name, r.student_id) for r in entries] == [("Tan, Alex", "A1"), ("Bea", "")]
    assert parse_roster_csv(b"name\nAlex\n")[0].student_id == ""


@pytest.mark.parametrize("csv", [
    b"student_id,full_name\nA1,Alex", b"student_id\nA1",
    b"name,name\nAlex,Bea", b"name,student_id\n,A1",
    b"name,student_id\nAlex,A1\nBea,a1", b"Alex,A1,extra",
    b'name,student_id\n"Alex,A1', b"name\n\xff",
])
def test_roster_rejects_invalid_input(csv):
    with pytest.raises(ValueError):
        parse_roster_csv(csv)
