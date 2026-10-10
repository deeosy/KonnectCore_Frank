"""Site-wide form rendering defaults.

Django appends ":" to every form label by default. The KonnectCore UI shows
labels above their fields, where the colon only adds noise, so this renderer
uses a bound field whose default label suffix is empty.

An explicit ``label_suffix`` passed to a form, field or ``label_tag`` call
still takes precedence.
"""
from django.forms.boundfield import BoundField
from django.forms.renderers import DjangoTemplates


class NoSuffixBoundField(BoundField):
    def label_tag(self, contents=None, attrs=None, label_suffix=None, tag=None):
        if label_suffix is None and self.field.label_suffix is None and self.form.label_suffix == ":":
            label_suffix = ""
        return super().label_tag(contents, attrs, label_suffix, tag)


class FormRenderer(DjangoTemplates):
    bound_field_class = NoSuffixBoundField
