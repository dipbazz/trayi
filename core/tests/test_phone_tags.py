from django.template import Context, Template

from core.templatetags.phone_tags import tel_href


class TestTelHref:
    def test_a_number_written_the_local_way_gets_its_country_code(self):
        assert tel_href("01-4567890", "NP") == "tel:+97714567890"

    def test_a_number_with_its_own_country_code_keeps_it(self):
        assert tel_href("+44 121 234 5678", "NP") == "tel:+441212345678"

    def test_of_several_numbers_the_first_is_linked(self):
        assert tel_href("01-4123456, 9841234567", "NP") == "tel:+97714123456"

    def test_a_number_with_an_extension_links_the_number(self):
        assert tel_href("+977 1 4123456 ext 12", "NP") == "tel:+97714123456"

    def test_a_number_that_cant_be_read_gives_no_link(self):
        # Without its country code it would fail for a supporter calling from abroad.
        assert tel_href("0123 456 7890", "NP") == ""
        assert tel_href("12+34", "NP") == ""

    def test_no_number_gives_no_link(self):
        assert tel_href("", "NP") == ""

    def test_it_is_a_template_filter(self):
        template = Template("{% load phone_tags %}{{ phone|tel_href:'NP' }}")

        assert template.render(Context({"phone": "01-4567890"})) == "tel:+97714567890"
