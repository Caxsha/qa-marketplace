import pytest

# Какая-то функция логики (например, расчет цены со скидкой в магазине)
def calculate_discount(price: float, percent: float) -> float:
    if price < 0 or percent < 0:
        raise ValueError("Цена и процент не могут быть отрицательными")
    return price * (1 - percent / 100)


# 1. Простой классический тест
def test_calculate_discount_standard():
    result = calculate_discount(1000, 20)
    assert result == 800.0


# 2. Параметризованный тест (один тест для разных входных данных)
@pytest.mark.parametrize("price, percent, expected", [
    (2000, 50, 1000.0),
    (100, 10, 90.0),
    (50, 100, 0.0),
])
def test_calculate_discount_parametrized(price, percent, expected):
    assert calculate_discount(price, percent) == expected


# 3. Проверка того, что функция выбрасывает ошибку
def test_calculate_discount_raises_error():
    with pytest.raises(ValueError, match="не могут быть отрицательными"):
        calculate_discount(-100, 10)