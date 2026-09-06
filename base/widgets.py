from django import forms
from django.utils.safestring import mark_safe


class CustomModelChoiceWidget(forms.Select):
    """
    A custom Django widget for rendering a select input with an optional delete button.

    This widget extends the standard Select widget to include a delete button.
    The URL for the delete action can be dynamically provided via the widget's
    attributes or constructor.

    Attributes:
        delete_url (str): The URL to be used for the delete button's action.
                        If not provided, the button will not be rendered.
    """

    def __init__(self, *args, **kwargs):
        # Remove default delete_url
        self.delete_url = None
        if "delete_url" in kwargs:
            self.delete_url = kwargs.pop("delete_url")
        super().__init__(*args, **kwargs)

    def render(self, name, value, attrs=None, renderer=None):
        attrs = attrs.copy() if attrs else {}
        # .oh-input/.oh-select carry a spacing margin-bottom (theme
        # v1_styles.css) that skews this flex row's vertical centering
        # against the delete button - the row spaces itself, so drop it.
        style = attrs.get("style", "")
        attrs["style"] = f"{style}; margin-bottom: 0" if style else "margin-bottom: 0"

        # Render the original widget
        original_html = super().render(name, value, attrs, renderer)

        # Get the delete_url from attributes if provided
        delete_url = attrs.get("delete_url", self.delete_url)

        # Create the custom HTML including the delete button
        custom_html = f"""
        <div class="pt-2" id="{name}">
            <div class="oh-input__group" style="display: flex; align-items: center; gap: 8px">
                <div style="flex: 1">{original_html}</div>
                {f'<button hx-get="{delete_url}" class="oh-btn oh-btn--danger oh-btn--sq-sm d-flex align-items-center justify-content-center flex-shrink-0" hx-target="#{name}" hx-swap="outerHTML" id="delete-link"><ion-icon name="trash-outline"></ion-icon></button>' if delete_url else ''}
            </div>
        </div>
        """
        return mark_safe(custom_html)

    from django import forms


class CustomTextInputWidget(forms.TextInput):
    """
    A custom Django widget for rendering a text input with an optional delete button.

    This widget extends the standard TextInput widget to include a delete button.
    The URL for the delete action can be dynamically provided via the widget's
    attributes or constructor.

    Attributes:
        delete_url (str): The URL to be used for the delete button's action.
                        If not provided, the button will not be rendered.
    """

    def __init__(self, *args, **kwargs):
        # Remove default delete_url
        self.delete_url = None
        if "delete_url" in kwargs:
            self.delete_url = kwargs.pop("delete_url")
        super().__init__(*args, **kwargs)

    def render(self, name, value, attrs=None, renderer=None):
        attrs = attrs.copy() if attrs else {}
        # .oh-input/.oh-select carry a spacing margin-bottom (theme
        # v1_styles.css) that skews this flex row's vertical centering
        # against the delete button - the row spaces itself, so drop it.
        style = attrs.get("style", "")
        attrs["style"] = f"{style}; margin-bottom: 0" if style else "margin-bottom: 0"

        # Render the original text input widget
        original_html = super().render(name, value, attrs, renderer)

        # Get the delete_url from attributes if provided
        delete_url = attrs.get("delete_url", self.delete_url)

        # Create the custom HTML including the delete button
        custom_html = f"""
        <div class="pt-2" id="{name}">
            <div class="oh-input__group" style="display: flex; align-items: center; gap: 8px">
                <div style="flex: 1">{original_html}</div>
                {f'<button hx-get="{delete_url}" class="oh-btn oh-btn--danger oh-btn--sq-sm d-flex align-items-center justify-content-center flex-shrink-0" hx-target="#{name}" hx-swap="outerHTML" id="delete-link"><ion-icon name="trash-outline"></ion-icon></button>' if delete_url else ''}
            </div>
        </div>
        """
        return mark_safe(custom_html)
