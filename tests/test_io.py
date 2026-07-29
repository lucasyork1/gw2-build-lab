from gw2_wvw_data.io import canonical_json_bytes


def test_canonical_json_is_sorted_utf8_and_newline_terminated():
    assert canonical_json_bytes({"z": 1, "a": "盗贼"}) == (
        b'{\n  "a": "\xe7\x9b\x97\xe8\xb4\xbc",\n  "z": 1\n}\n'
    )
