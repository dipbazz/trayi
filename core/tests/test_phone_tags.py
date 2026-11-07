from django.template import Context, Template

from core.templatetags.phone_tags import tel_href


class TestTelHref:
    def test_a_number_written_the_local_way_gets_its_country_code(self):
        assert tel_href("01-4567890", "NP") == "tel:+97714567890"

    def test_a_number_with_its_own_country_code_keeps_it(self):
        assert tel_href("+44 121 234 5678", "NP") == "tel:+441212345678"

    def test_a_number_that_cant_be_read_keeps_only_its_digits_and_a_leading_plus(self):
        assert tel_href("+977 (1) 4567 ext. 12", "NP") == "tel:+9771456712"

    def test_a_plus_inside_the_number_is_dropped(self):
        assert tel_href("12+34", "NP") == "tel:1234"

    def test_no_number_gives_no_link(self):
        assert tel_href("", "NP") == ""

    def test_it_is_a_template_filter(self):
        template = Template("{% load phone_tags %}{{ phone|tel_href:'NP' }}")

        assert template.render(Context({"phone": "01-4567890"})) == "tel:+97714567890"
