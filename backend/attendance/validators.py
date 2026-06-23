import re
from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _


class UppercaseValidator:
    """Require at least one uppercase letter."""

    def validate(self, password, user=None):
        if not re.search(r'[A-Z]', password):
            raise ValidationError(
                _('Kata laluan mesti mengandungi sekurang-kurangnya satu huruf besar.'),
                code='password_no_upper',
            )

    def get_help_text(self):
        return _('Kata laluan mesti mengandungi sekurang-kurangnya satu huruf besar.')


class LowercaseValidator:
    """Require at least one lowercase letter."""

    def validate(self, password, user=None):
        if not re.search(r'[a-z]', password):
            raise ValidationError(
                _('Kata laluan mesti mengandungi sekurang-kurangnya satu huruf kecil.'),
                code='password_no_lower',
            )

    def get_help_text(self):
        return _('Kata laluan mesti mengandungi sekurang-kurangnya satu huruf kecil.')


class DigitValidator:
    """Require at least one digit."""

    def validate(self, password, user=None):
        if not re.search(r'\d', password):
            raise ValidationError(
                _('Kata laluan mesti mengandungi sekurang-kurangnya satu nombor.'),
                code='password_no_digit',
            )

    def get_help_text(self):
        return _('Kata laluan mesti mengandungi sekurang-kurangnya satu nombor.')


class SpecialCharacterValidator:
    """Require at least one special character."""

    SPECIAL_CHARS = r'[!@#$%^&*()_+\-=\[\]{};\':"\\|,.<>\/?`~]'

    def validate(self, password, user=None):
        if not re.search(self.SPECIAL_CHARS, password):
            raise ValidationError(
                _('Kata laluan mesti mengandungi sekurang-kurangnya satu aksara istimewa.'),
                code='password_no_special',
            )

    def get_help_text(self):
        return _('Kata laluan mesti mengandungi sekurang-kurangnya satu aksara istimewa.')
