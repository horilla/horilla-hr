"""
Module: resources.py
This module defines classes for handling resources related to assets.
"""

from import_export import resources

from .models import Asset


class AssetResource(resources.ModelResource):
    """
    This class is used to import and export Asset data using the import_export library.
    """

    class Meta:
        """
        Specifies the model to be used for import and export.
        """

        model = Asset
