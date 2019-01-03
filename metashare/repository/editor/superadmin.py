'''
Custom base classes for admin interface, for both the top-level admin page
and for inline forms.
'''
import logging

from django import template
from django.conf import settings
from django.contrib import admin, messages
from django.contrib.admin import helpers
from django.contrib.admin.exceptions import DisallowedModelAdminToField
from django.contrib.admin.options import IS_POPUP_VAR, TO_FIELD_VAR
from django.contrib.admin.templatetags.admin_urls import add_preserved_filters
from django.contrib.admin.utils import unquote
from django.core.exceptions import PermissionDenied
from django.core.urlresolvers import reverse
from django.db import transaction, models, router
from django.forms.formsets import all_valid
from django.http import Http404, HttpResponse, HttpResponseRedirect
from django.shortcuts import render_to_response
from django.utils.decorators import method_decorator
from django.utils.encoding import force_unicode, force_text
from django.utils.html import escape, escapejs
from django.utils.translation import ugettext as _
from django.views.decorators.csrf import csrf_protect

from metashare.repository import model_utils
from metashare.repository.editor.editorutils import is_inline, decode_inline, \
    MetaShareSearchModelAdmin
from metashare.repository.editor.inlines import ReverseInlineModelAdmin
from metashare.repository.editor.related_mixin import RelatedAdminMixin
from metashare.repository.editor.schemamodel_mixin import SchemaModelLookup
from metashare.repository.model_utils import get_root_resources
from metashare.repository.supermodel import REQUIRED, RECOMMENDED, OPTIONAL
from metashare.storage.models import MASTER

IS_POPUP_O2M_VAR = '_popup_o2m'

# Setup logging support.
LOGGER = logging.getLogger(__name__)
LOGGER.addHandler(settings.LOG_HANDLER)

csrf_protect_m = method_decorator(csrf_protect)


class SchemaModelAdmin(MetaShareSearchModelAdmin, RelatedAdminMixin, SchemaModelLookup):
    '''
    Patched ModelAdmin class. The add_view method is overridden to
    allow the reverse inline formsets to be saved before the parent
    model.
    '''
    custom_one2one_inlines = {}
    custom_one2many_inlines = {}
    inline_type = 'stacked'
    inlines = ()

    class Media:
        js = (settings.STATIC_URL + 'metashare/js/addCollapseToAllStackedInlines.js',
              settings.STATIC_URL + 'metashare/js/jquery-ui.min.js',
              settings.STATIC_URL + 'metashare/js/help.js',
              settings.STATIC_URL + 'admin/js/collapse.min.js',)
        css = {'all': (settings.STATIC_URL + 'admin/css/themes/smoothness/jquery-ui.css',)}

    def __init__(self, model, admin_site):
        # Get from the model all inlines grouped by Required/Recommended/Optional status:
        self.inlines += tuple(self.get_inline_classes(model, status=REQUIRED) + \
          self.get_inline_classes(model, status=RECOMMENDED) + \
          self.get_inline_classes(model, status=OPTIONAL))
        # Show m2m fields as horizontal filter widget unless they have a custom widget:
        self.filter_horizontal = self.list_m2m_fields_without_custom_widget(model)
        super(SchemaModelAdmin, self).__init__(model, admin_site)
        # Reverse inline code:
        self.no_inlines = []
        self.exclude = self.exclude or []
        if not isinstance(self.exclude, list):
            self.exclude = list(self.exclude)
        self.tmp_inline_instances = []
        # Prepare inlines for the required one2one fields:
        for field in model._meta.fields:
            if isinstance(field, models.OneToOneField):
                name = field.name
                if not name in self.no_inlines and not name in self.exclude and not name in self.readonly_fields:
                    if self.contains_inlines(field.rel.to):
                        # ignore fields referring to models that "contain"
                        # inlines; if we wouldn't ignore these, these
                        # inlines would simply not show up because of the
                        # internal nested structure
                        self.no_inlines.append(name)
                        continue
                    parent = field.related.parent_model
                    if name == '{}_ptr'.format(parent.__name__.lower()):
                        # ignore fields generated by Django because of model
                        # inheritance (?)
                        self.no_inlines.append(name)
                        continue
                    _inline_class = ReverseInlineModelAdmin
                    if name in self.custom_one2one_inlines:
                        _inline_class = self.custom_one2one_inlines[name]
                    inline = _inline_class(model,
                                           name,
                                           parent,
                                           admin_site,
                                           self.inline_type)
                    self.tmp_inline_instances.append(inline)
                    self.exclude.append(name)

    def get_inline_instances(self, request, obj=None):
        return self.tmp_inline_instances + super(SchemaModelAdmin, self).get_inline_instances(request)

    def get_actions(self, request):
        """
        Return a dictionary mapping the names of all actions for this
        `ModelAdmin` to a tuple of (callable, name, description) for each
        action.
        """
        result = super(SchemaModelAdmin, self).get_actions(request)
        if not request.user.is_superuser:
            # only superusers can see the delete action; this makes sense as
            # currently deleting would mostly not work anyway due to related
            # objects which can't be deleted
            del result['delete_selected']
        return result

    def contains_inlines(self, model_class):
        '''
        Determine whether or not the editor for the given model_class will
        contain inlines
        '''
        return any(f for f in model_class.get_fields_flat() if f.endswith('_set'))

    def get_fieldsets(self, request, obj=None):
        return SchemaModelLookup.get_fieldsets(self, request, obj)

    def formfield_for_dbfield(self, db_field, **kwargs):
        """
        This is a crucial step in the workflow: for a given db field,
        it is decided how this field will be rendered in the form.
        We have heavily customized this; implementations are in
        RelatedAdminMixin.

        Customizations include:
        - hiding certain fields (they are present but invisible);
        - custom widgets for subclassable items such as actorInfo;
        - custom minimalistic "related" widget for non-inlined one2one fields;
        """
        self.hide_hidden_fields(db_field, kwargs)
        # ForeignKey or ManyToManyFields
        if self.is_x_to_many_relation(db_field):
            return self.formfield_for_relation(db_field, **kwargs)
        self.use_hidden_widget_for_one2one(db_field, kwargs)
        lang_widget = self.add_lang_widget(db_field)
        kwargs.update(lang_widget)
        formfield = super(SchemaModelAdmin, self).formfield_for_dbfield(db_field, **kwargs)
        self.use_related_widget_where_appropriate(db_field, kwargs, formfield)
        return formfield

    def has_change_permission(self, request, obj=None):
        result = super(SchemaModelAdmin, self) \
            .has_change_permission(request, obj)
        if result and obj:
            if request.user.is_superuser or request.user.is_staff:
                return True
            # find out to which resourceInfoType_model instance the obj belongs
            root_resources = get_root_resources(obj)
            if len(root_resources) == 0:
                # some model instances are created before the (future) root
                # resource is actually saved, e.g., toolServiceInfo; in this
                # case the user is probably in the process of editing this model
                # instance and therefore we have to allow her to change it
                return True
            # in addition to the default change permission determination, we
            # only allow a user to edit a model if she is either owner or an
            # authorized editor of the resource to which the model belongs
            usr_grp_names = request.user.groups.values_list('name', flat=True)
            for res in root_resources:
                if request.user in res.owners.all() \
                        or any(res_group.name in usr_grp_names
                               for res_group in res.editor_groups.all()):
                    return True
            return False
        return result

    def response_add(self, request, obj, post_url_continue=None):
        if IS_POPUP_VAR in request.REQUEST:
            if '_subclass' in request.REQUEST:
                pk_value = obj._get_pk_val()
                class_name = obj.__class__.__name__.lower()
                return HttpResponse('<script type="text/javascript">opener.dismissAddAnotherPopup(window, "%s", "%s", "%s");</script>' % \
                    # escape() calls force_unicode.
                    (escape(pk_value), escapejs(obj), escapejs(class_name)))
        return super(SchemaModelAdmin, self).response_add(request, obj, post_url_continue)

    def response_change(self, request, obj):
        '''
        Response sent after a successful submission of a change form.
        We customize this to allow closing edit popups in the same way
        as response_add deals with add popups.
        '''

        # Custom messages for upload actions. A dictionary using POST._back-from as key
        BACK_FROM_SUCCESS = {
            '/upload-legal/': 'The legal documentation',
            '/upload-data/': 'The dataset',
            '/upload-report/': 'The validation report'
        }

        if IS_POPUP_O2M_VAR in request.REQUEST:
            caller = None
            if '_caller' in request.REQUEST:
                caller = request.REQUEST['_caller']
            return self.edit_response_close_popup_magic_o2m(obj, caller)
        elif IS_POPUP_VAR in request.REQUEST:
            if request.POST.has_key("_continue"):
                return self.save_and_continue_in_popup(obj, request)
            return self.edit_response_close_popup_magic(obj)
        elif "_back-from" in request.POST:
            opts = self.model._meta

            msg = "{} for LR #{} was uploaded successfully. You may continue editing the resource metadata.".format(
                BACK_FROM_SUCCESS[request.POST['_back-from']], obj.id
            )
            preserved_filters = self.get_preserved_filters(request)
            self.message_user(request, msg, messages.SUCCESS)
            redirect_url = request.META['HTTP_REFERER'].replace(request.POST['_back-from'], '')
            redirect_url = add_preserved_filters({'preserved_filters': preserved_filters, 'opts': opts}, redirect_url)
            return HttpResponseRedirect(redirect_url)
        else:
            return super(SchemaModelAdmin, self).response_change(request, obj)

    def response_delete(self, request, obj_display):
        '''
        Response sent after a successful deletion.
        '''
        if IS_POPUP_VAR in request.REQUEST:
            return HttpResponse('<script type="text/javascript">opener.dismissDeleteRelatedPopup(window);</script>')
        return self.response_delete(request, obj_display)

    def set_required_formset(self, formset):
        req_forms = formset.forms
        for req_form in req_forms:
            if not 'DELETE' in req_form.changed_data:
                req_form.empty_permitted = False
                break

    def get_inline_formsets(self, request, formsets, inline_instances,
                            obj=None):
        inline_admin_formsets = []
        for inline, formset in zip(inline_instances, formsets):
            fieldsets = list(inline.get_fieldsets(request, obj))
            readonly = list(inline.get_readonly_fields(request, obj))
            prepopulated = dict(inline.get_prepopulated_fields(request, obj))
            inline_admin_formset = helpers.InlineAdminFormSet(inline, formset,
                fieldsets, prepopulated, readonly, model_admin=self)
            #### begin modification ####
            self.add_lang_templ_params(inline_admin_formset)
            #### end modification ####
            inline_admin_formsets.append(inline_admin_formset)
        return inline_admin_formsets

    @csrf_protect_m
    @transaction.atomic
    def changeform_view(self, request, object_id=None, form_url='', extra_context=None):
        """
        This follows closely the base implementation from Django 1.7's
        django.contrib.admin.options.ModelAdmin,
        with the explicitly marked modifications.
        """
        to_field = request.POST.get(TO_FIELD_VAR, request.GET.get(TO_FIELD_VAR))
        if to_field and not self.to_field_allowed(request, to_field):
            raise DisallowedModelAdminToField("The field %s cannot be referenced." % to_field)

        model = self.model
        opts = model._meta
        add = object_id is None

        if add:
            if not self.has_add_permission(request):
                raise PermissionDenied
            obj = None

        else:
            obj = self.get_object(request, unquote(object_id))

            if not self.has_change_permission(request, obj):
                raise PermissionDenied

            if obj is None:
                raise Http404(_('%(name)s object with primary key %(key)r does not exist.') % {
                    'name': force_text(opts.verbose_name), 'key': escape(object_id)})

            if request.method == 'POST' and "_saveasnew" in request.POST:
                return self.add_view(request, form_url=reverse('admin:%s_%s_add' % (
                    opts.app_label, opts.model_name),
                    current_app=self.admin_site.name))

        #### begin modification ####
        # make sure that the user has a full session length time for the current
        # edit activity
        request.session.set_expiry(settings.SESSION_COOKIE_AGE)
        #### end modification ####

        ModelForm = self.get_form(request, obj)
        if request.method == 'POST':
            form = ModelForm(request.POST, request.FILES, instance=obj)
            if form.is_valid():
                form_validated = True
                new_object = self.save_form(request, form, change=not add)
            else:
                form_validated = False
                new_object = form.instance
            formsets, inline_instances = self._create_formsets(request, new_object, change=not add)
            if all_valid(formsets) and form_validated:
                #### begin modification ####
                unsaved_formsets = []
                for formset in formsets:
                    parent_fk_name = getattr(formset, 'parent_fk_name', '')
                    # for the moment ignore all formsets that are no reverse
                    # inlines
                    if add:
                        if not parent_fk_name:
                            unsaved_formsets.append(formset)
                            continue

                    # this replaces the call to self.save_formsets()
                    changes = formset.save()
                    # if there are any changes in the current inline and if this
                    # inline is a reverse inline, then we need to manually make
                    # sure that the inline data is connected to the parent
                    # object:
                    if changes:
                        if parent_fk_name:
                            assert len(changes) == 1
                            setattr(new_object, parent_fk_name, changes[0])

                    # If we have deleted a one-to-one inline, we must manually
                    # unset the field value.
                    if formset.deleted_objects:
                        if parent_fk_name:
                            setattr(new_object, parent_fk_name, None)

                self.save_model(request, new_object, form, not add)
                form.save_m2m()

                for formset in unsaved_formsets:
                    self.save_formset(request, form, formset, add)

                # for resource info, explicitly write its metadata XML and
                # storage object to the storage folder
                if self.model.__schema_name__ == "resourceInfo":
                    new_object.storage_object.update_storage()
                #### end modification ####
                if add:
                    self.log_addition(request, new_object)
                    return self.response_add(request, new_object)
                else:
                    change_message = self.construct_change_message(request, form, formsets)
                    self.log_change(request, new_object, change_message)
                    return self.response_change(request, new_object)
        else:
            if add:
                initial = self.get_changeform_initial_data(request)
                form = ModelForm(initial=initial)
                formsets, inline_instances = self._create_formsets(request, self.model(), change=False)
            else:
                form = ModelForm(instance=obj)
                formsets, inline_instances = self._create_formsets(request, obj, change=True)

        #### begin modification ####
        media = self.media or []
        #### end modification ####

        inline_formsets = self.get_inline_formsets(request, formsets, inline_instances, obj)
        for inline_formset in inline_formsets:
            media = media + inline_formset.media

        #### begin modification ####
        adminForm = OrderedAdminForm(form, list(self.get_fieldsets_with_inlines(request)),
            self.prepopulated_fields, self.get_readonly_fields(request, obj),
            model_admin=self, inlines=inline_formsets)
        media = media + adminForm.media
        #### end modification ####

        context = dict(self.admin_site.each_context(),
            title=(_('Add %s') if add else _('Change %s')) % force_text(opts.verbose_name),
            adminform=adminForm,
            object_id=object_id,
            original=obj,
            is_popup=(IS_POPUP_VAR in request.REQUEST or \
                      IS_POPUP_O2M_VAR in request.REQUEST),
            to_field=to_field,
            media=media,
            inline_admin_formsets=inline_formsets,
            errors=helpers.AdminErrorList(form, formsets),
            preserved_filters=self.get_preserved_filters(request),
            kb_link=settings.KNOWLEDGE_BASE_URL,
            app_label=opts.app_label,
            show_delete=False,
        )
    
        context.update(extra_context or {})

        #### begin modification ####
        if not add:
            # redirection for reusable entities which are no master copies:
            if hasattr(obj, 'copy_status') and obj.copy_status != MASTER:
                context['url'] = obj.source_url
                context_instance = template.RequestContext(
                    request, current_app=self.admin_site.name)
                return render_to_response('admin/repository/cannot_edit.html',
                    context, context_instance=context_instance)
            # redirection for resources and their parts which are no master copies:
            else:
                for res in [r for r in get_root_resources(obj)
                            if not r.storage_object.master_copy]:
                    context['redirection_url'] = model_utils.get_lr_master_url(res)
                    context['resource'] = res
                    context_instance = template.RequestContext(
                        request, current_app=self.admin_site.name)
                    return render_to_response('admin/repository/cannot_edit.html',
                        context, context_instance=context_instance)
        #### end modification ####
        return self.render_change_form(request, context, add=add, change=not add, obj=obj, form_url=form_url)

    def _create_formsets(self, request, obj, change):
        "Helper function to generate formsets for add/change_view."
        formsets = []
        inline_instances = []
        prefixes = {}
        get_formsets_args = [request]
        if change:
            get_formsets_args.append(obj)
        for FormSet, inline in self.get_formsets_with_inlines(*get_formsets_args):
            #### begin modification ####
            if getattr(FormSet, 'parent_fk_name', None) in self.no_inlines:
                continue
            #### end modification ####
            prefix = FormSet.get_default_prefix()
            prefixes[prefix] = prefixes.get(prefix, 0) + 1
            if prefixes[prefix] != 1 or not prefix:
                prefix = "%s-%s" % (prefix, prefixes[prefix])
            formset_params = {
                'instance': obj,
                'prefix': prefix,
                'queryset': inline.get_queryset(request),
            }
            if request.method == 'POST':
                formset_params.update({
                    'data': request.POST,
                    'files': request.FILES,
                    'save_as_new': '_saveasnew' in request.POST
                })
            #### begin modification ####
            formset = FormSet(**formset_params)
            if request.method == 'POST' and prefix in self.model.get_fields()['required']:
                self.set_required_formset(formset)
            formsets.append(formset)
            #### end modification ####
            inline_instances.append(inline)
        return formsets, inline_instances

class OrderedAdminForm(helpers.AdminForm):
    
    def __init__(self, form, fieldsets, prepopulated_fields, readonly_fields=None, model_admin=None, inlines=None):
        self.inlines = inlines
        super(OrderedAdminForm, self).__init__(form, fieldsets, prepopulated_fields, readonly_fields, model_admin)

    def __iter__(self):
        for name, options in self.fieldsets:
            yield OrderedFieldset(self.form, name,
                readonly_fields=self.readonly_fields,
                model_admin=self.model_admin, inlines=self.inlines,
                **options
            )

class OrderedFieldset(helpers.Fieldset):
    def __init__(self, form, name=None, readonly_fields=(), fields=(), classes=(),
      description=None, model_admin=None, inlines=None):
        self.inlines = inlines
        if not inlines:
            for field in fields:
                if is_inline(field):
                    # an inline is in the field list, but the list of inlines is empty
                    pass
        super(OrderedFieldset, self).__init__(form, name, readonly_fields, fields, classes, description, model_admin)

    def __iter__(self):
        for field in self.fields:
            if not is_inline(field):
                fieldline = helpers.Fieldline(self.form, field, self.readonly_fields, model_admin=self.model_admin)
                help_link = u'%s%s' % (settings.KNOWLEDGE_BASE_URL, field)
                elem = OrderedElement(fieldline=fieldline, help_link=help_link)
                yield elem
            else:
                field = decode_inline(field)
                for inline in self.inlines:
                    if hasattr(inline.opts, 'parent_fk_name'):
                        if inline.opts.parent_fk_name == field:
                            help_link = u'%s%s' % (settings.KNOWLEDGE_BASE_URL, field)
                            elem = OrderedElement(inline=inline, help_link=help_link)
                            yield elem
                    elif hasattr(inline.formset, 'prefix'):
                        if inline.formset.prefix == field:
                            elem = OrderedElement(inline=inline)
                            yield elem
                    else:
                        raise InlineError('Incorrect inline: no opts.parent_fk_name or formset.prefix found')


class OrderedElement():
    def __init__(self, fieldline=None, inline=None, help_link=None):
        if fieldline:
            self.is_field = True
            self.fieldline = fieldline
            self.help_link = help_link
        else:
            self.is_field = False
            self.inline = inline
            self.help_link = help_link


class InlineError(Exception):
    def __init__(self, msg=None):
        super(InlineError, self).__init__()
        self.msg = msg
