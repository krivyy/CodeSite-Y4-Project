def test_largest_first_number():
    assert largest(10, 5) == 10


def test_largest_second_number():
    assert largest(3, 8) == 8


def test_largest_equal_numbers():
    assert largest(4, 4) == 4