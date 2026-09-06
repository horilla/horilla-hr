"""
Register a custom filter called get_item for retrieving values from dictionaries by key.
"""

from django import template

register = template.Library()


@register.filter(name="get_item")
def get_item(dictionary, key):
    """
    Retrieve a value from a dictionary using the given key.

    Args:
        dictionary (dict): The dictionary from which to retrieve the value.
        key: The key whose value is to be retrieved from the dictionary.

    Returns:
        The value associated with the specified key in the dictionary.
    """
    return dictionary.get(key)
