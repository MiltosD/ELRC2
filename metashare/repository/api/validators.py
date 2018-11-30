from django.db.models import FieldDoesNotExist

from tastypie.validation import Validation

EXCLUDES = ('copy_status', 'source_url')


class ELRCValidation(Validation):
    """
    Given a model, return a list of fields that define choices and validate incoming values against them
    """
    model = None

    def is_required(self, field):
        if field.name not in EXCLUDES:
            if not field.blank and not field.null:
                return True
        return False

    def __init__(self, model=None):
        self.model = model
        super(ELRCValidation, self).__init__()

    def _get_model_choice_fields(self):
        fields_choices = []
        all_fields = self.model._meta.fields
        for field in all_fields:
            try:
                if field.choices:
                    fields_choices.append(field)
            except FieldDoesNotExist:
                pass
        return fields_choices

    def _choices(self, field):
        return [v[0] for v in field.get_flatchoices(False)]

    def is_valid(self, bundle, request=None):
        errors = []

        for field in self._get_model_choice_fields():
            value_to_check = bundle.data.get(field.name)

            if not value_to_check and self.is_required(field):
                errors.append("{} is required for {}".format(field.name, self.model))

            if value_to_check:
                if isinstance(value_to_check, list):
                    for value_to_check in value_to_check:
                        if value_to_check not in self._choices(field):
                            errors.append("'{}' is not a valid choice for {}.{}".format(
                                value_to_check, self.model._meta.verbose_name, field.name))
                else:
                    if value_to_check not in self._choices(field):
                        errors.append("'{}' is not a valid choice for {}.{}".format(
                            value_to_check, self.model._meta.verbose_name, field.name))
        return errors
