# ruff: noqa: E402
import logging

logger = logging.getLogger(__name__)

from django import forms
from django.contrib import admin
from django.contrib.auth.admin import GroupAdmin, UserAdmin
from django.contrib.auth.models import Group
from lick_archive.apps.archive_auth.models import (
    ArchiveUser,
    DBOverrideAccessFile,
    DBOverrideAccessRule,
)
from lick_archive.config.archive_config import ArchiveConfigFile

lick_archive_config = ArchiveConfigFile.load_from_standard_inifile().config


class LickArchiveAdminSite(admin.AdminSite):
    site_header = "Mt. Hamilton Data Repository Administration"
    site_title = "Mt. Hamilton Data Repository Admin"
    site_url = lick_archive_config.host.frontend_url + "/index.html"

    # The custom sections and models we want to organize the admin site by
    # The section name references the "app_label" in the original "available_apps"
    # context value and the models are referred to by their class name
    sections = {
        "archive_auth": [str(ArchiveUser), str(Group), str(DBOverrideAccessFile)]
    }

    def get_app_list(self, request, app_label=None):
        """The Django Admin site organizes it's side bar into apps. But that looks bad when we've customized
        every model *except* the "Group" model, resulting in one section for Groups, and one section for everything else.

        So we override this method to return "available_apps" in a way that groups everything into the sections and models
        defined in the ``sections`` class member.
        """
        if app_label is not None and app_label not in self.sections:
            # Deny the existence of apps not in our sections class variable
            return []

        # Get all app information regardless of whether app_label was passed, as we may pull models from multiple apps
        app_list = super().get_app_list(request)

        logger.debug(f"Orig app_list: {app_list}")
        if len(app_list) == 0:
            return app_list

        # Organize the returned list into easier to use dicts
        app_dict = {}
        model_dict = {}
        for app in app_list:
            app_dict[app["app_label"]] = app
            for model in app["models"]:
                model_dict[str(model["model"])] = model

        # Create a reorganized list
        new_app_list = []
        app_labels = [app_label] if app_label is not None else self.sections.keys()
        for section in app_labels:
            app = app_dict[section]
            app["models"] = []
            for model_name in self.sections[section]:
                app["models"].append(model_dict[model_name])
            new_app_list.append(app)
        logger.debug(f"New app_list: {new_app_list}")
        return new_app_list


class OverrideAccessRuleForm(forms.ModelForm):
    class Meta:
        model = DBOverrideAccessRule
        fields = ["pattern", "type", "access"]

    ownerhints = forms.CharField(
        required=False, label="Ownerhints", widget=forms.Textarea
    )

    def __init__(self, *args, **kwargs):

        instance = kwargs.get("instance", None)
        if instance is not None:
            if instance.access == "ownerhints":
                # Add ownerhints to the ownerhints field
                ownerhints_text = ",\n".join(
                    [f"{oh.ownerhint}" for oh in instance.ownerhints.all()]
                )
                kwargs["initial"] = {"ownerhints": ownerhints_text}

        logger.debug(f"Initializing OverrideAccessRuleForm with {args} and {kwargs}")
        super().__init__(*args, **kwargs)

    def save(self, commit=True):
        # Add the ownerhints data to the model instance before saving
        logger.debug(
            f"Saving Override Access rule {self.instance.file} {self.instance}"
        )

        saved_instance = super().save(commit)

        # Clear out previous owner hints, either we'll reset them to the new values, or
        # the access type changed so that ownerhints are no longer needed
        saved_instance.ownerhints.all().delete()

        if saved_instance.access == "ownerhints":
            # Ownerhints are entered as comma separated values with optional surrounding whitespace
            ownerhints = [
                hint.strip() for hint in self.cleaned_data["ownerhints"].split(",")
            ]
            logger.debug(f"Saving ownerhints: {ownerhints}")
            for hint in ownerhints:
                saved_instance.ownerhints.create(ownerhint=hint)

        return super().save(commit)


class OverrideAccessRuleInline(admin.StackedInline):
    class Media:
        css = {"all": ["archive_admin/archive_admin.css"]}

    model = DBOverrideAccessRule
    form = OverrideAccessRuleForm
    extra = 1
    radio_fields = {"type": admin.HORIZONTAL, "access": admin.VERTICAL}


class OverrideAccessFileAdmin(admin.ModelAdmin):
    class Media:
        css = {"all": ["archive_admin/archive_admin.css"]}

    inlines = [OverrideAccessRuleInline]

    radio_fields = {"instrument_dir": admin.HORIZONTAL}

    # def get_formsets_with_inlines(self, request, obj):
    #    return super().get_formsets_with_inlines(request, obj)


# Register your models here.
admin_site = LickArchiveAdminSite()
admin_site.register(ArchiveUser, UserAdmin)
admin_site.register(Group, GroupAdmin)
admin_site.register(DBOverrideAccessFile, OverrideAccessFileAdmin)
