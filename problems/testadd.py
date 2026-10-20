def test_add_positive_numbers():
    assert add(3, 5) == 8


def test_add_larger_numbers():
    assert add(10, 20) == 30


def test_add_negative_number():
    assert add(-2, 2) == 0