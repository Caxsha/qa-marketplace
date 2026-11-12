import os
import unittest
from uuid import uuid4

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None


BASE_URL = os.getenv("E2E_BASE_URL", "").rstrip("/")
ADMIN_EMAIL = os.getenv("E2E_ADMIN_EMAIL", "")
ADMIN_PASSWORD = os.getenv("E2E_ADMIN_PASSWORD", "")


@unittest.skipUnless(
    sync_playwright is not None and BASE_URL and ADMIN_EMAIL and ADMIN_PASSWORD,
    "Set E2E_BASE_URL and disposable E2E admin credentials to run browser E2E",
)
class DemoPaymentCheckoutE2ETests(unittest.TestCase):
    def test_customer_places_order_and_simulates_card_payment(self):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page()
            try:
                page.goto(f"{BASE_URL}/shop/register")
                page.get_by_label("Email").fill(f"qa-{uuid4().hex}@example.com")
                page.get_by_label("Пароль").fill("TestPass12345")
                page.get_by_label("Я принимаю политику конфиденциальности и оферту").check()
                page.get_by_role("button", name="Зарегистрироваться").click()
                page.wait_for_url(f"{BASE_URL}/shop")

                page.goto(f"{BASE_URL}/shop/catalog")
                product_card = page.locator(".item-card").filter(has_text="Домашние яйца")
                product_card.get_by_role("button", name="В корзину").click()
                page.get_by_text("Добавлено в корзину").wait_for()

                page.goto(f"{BASE_URL}/shop/cart")
                page.get_by_role("link", name="Оформить заказ").click()
                page.locator(".fulfillment-toggle .type-option").filter(
                    has_text="Самовывоз"
                ).click()
                page.get_by_role("button", name="Оформить заказ").click()
                page.wait_for_url(f"{BASE_URL}/shop/orders/**")
                page.get_by_text("Ожидает оплаты", exact=True).wait_for()

                page.get_by_role("button", name="Имитировать оплату картой").click()
                page.get_by_text("Оплачен", exact=True).wait_for()
                page.get_by_text("Реального списания не было.").wait_for()

                order_id = page.url.rsplit("/", 1)[-1]
                admin_page = browser.new_page()
                admin_page.goto(f"{BASE_URL}/shop/login")
                admin_page.get_by_label("Email").fill(ADMIN_EMAIL)
                admin_page.get_by_label("Пароль").fill(ADMIN_PASSWORD)
                admin_page.get_by_role("button", name="Войти").click()
                admin_page.wait_for_url(f"{BASE_URL}/shop")
                admin_page.goto(f"{BASE_URL}/shop/admin/orders/{order_id}")
                admin_page.get_by_role("heading", name=f"Заказ №{order_id}").wait_for()
                admin_page.get_by_text("Карта (демо)").wait_for()
                admin_page.get_by_text("succeeded").wait_for()
            finally:
                browser.close()


if __name__ == "__main__":
    unittest.main()
