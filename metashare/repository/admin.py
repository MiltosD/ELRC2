from django.contrib import admin
from metashare.repository.editor.superadmin import SchemaModelAdmin
from metashare.repository.editor.inlines import SchemaModelInline
from metashare.repository.forms import RelationsForm

from metashare.repository.models import documentUnstructuredString_model

admin.site.register(documentUnstructuredString_model)

from metashare.repository.models import \
    actorInfoType_model, \
    annotationInfoType_model, \
    characterEncodingInfoType_model, \
    communicationInfoType_model, \
    corpusInfoType_model, \
    corpusMediaTypeType_model, \
    corpusTextInfoType_model, \
    creationInfoType_model, \
    dependenciesInfoType_model, \
    distributionInfoType_model, \
    documentInfoType_model, \
    documentationInfoType_model, \
    domainInfoType_model, \
    domainSetInfoType_model, \
    identificationInfoType_model, \
    inputInfoType_model, \
    languageDescriptionEncodingInfoType_model, \
    languageDescriptionInfoType_model, \
    languageDescriptionMediaTypeType_model, \
    languageDescriptionTextInfoType_model, \
    languageInfoType_model, \
    languageSetInfoType_model, \
    languageVarietyInfoType_model, \
    lexicalConceptualResourceEncodingInfoType_model, \
    lexicalConceptualResourceInfoType_model, \
    lexicalConceptualResourceMediaTypeType_model, \
    lexicalConceptualResourceTextInfoType_model, \
    licenceInfoType_model, \
    lingualityInfoType_model, \
    metadataInfoType_model, \
    organizationInfoType_model, \
    outputInfoType_model, \
    personInfoType_model, \
    projectInfoType_model, \
    relationInfoType_model, \
    resourceComponentTypeType_model, \
    resourceCreationInfoType_model, \
    resourceDocumentationInfoType_model, \
    resourceInfoType_model, \
    sizeInfoType_model, \
    targetResourceInfoType_model, \
    textClassificationInfoType_model, \
    textFormatInfoType_model, \
    toolServiceCreationInfoType_model, \
    toolServiceEvaluationInfoType_model, \
    toolServiceInfoType_model, \
    toolServiceOperationInfoType_model, \
    validationInfoType_model, \
    versionInfoType_model


# pylint: disable-msg=C0103
class annotationInfo_model_inline(SchemaModelInline):
    model = annotationInfoType_model
    collapse = True


# pylint: disable-msg=C0103
class characterEncodingInfo_model_inline_corpusTextInfoType_model(SchemaModelInline):
    model = characterEncodingInfoType_model
    template = 'admin/edit_inline/tabular.html'
    fk_name = 'back_to_corpustextinfotype_model'


# pylint: disable-msg=C0103
class characterEncodingInfo_model_inline_languageDescriptionTextInfoType_model(SchemaModelInline):
    model = characterEncodingInfoType_model
    template = 'admin/edit_inline/tabular.html'
    fk_name = 'back_to_languagedescriptiontextinfotype_model'


# pylint: disable-msg=C0103
class characterEncodingInfo_model_inline_lexicalConceptualResourceTextInfoType_model(SchemaModelInline):
    model = characterEncodingInfoType_model
    template = 'admin/edit_inline/tabular.html'
    fk_name = 'back_to_lexicalconceptualresourcetextinfotype_model'


# pylint: disable-msg=C0103
class corpusInfo_model_inline(SchemaModelInline):
    model = corpusInfoType_model


# pylint: disable-msg=C0103
class corpusTextInfo_model_inline(SchemaModelInline):
    model = corpusTextInfoType_model


# pylint: disable-msg=C0103
class distributionInfo_model_inline(SchemaModelInline):
    model = distributionInfoType_model
    extra = 0
    min_num = 1


# pylint: disable-msg=C0103
class documentInfo_model_inline(SchemaModelInline):
    model = documentInfoType_model


# pylint: disable-msg=C0103
class domainInfo_model_inline_corpusTextInfoType_model(SchemaModelInline):
    model = domainInfoType_model
    template = 'admin/edit_inline/tabular.html'
    fk_name = 'back_to_corpustextinfotype_model'


# pylint: disable-msg=C0103
class domainInfo_model_inline_languageDescriptionTextInfoType_model(SchemaModelInline):
    model = domainInfoType_model
    template = 'admin/edit_inline/tabular.html'
    fk_name = 'back_to_languagedescriptiontextinfotype_model'


# pylint: disable-msg=C0103
class domainInfo_model_inline_lexicalConceptualResourceTextInfoType_model(SchemaModelInline):
    model = domainInfoType_model
    template = 'admin/edit_inline/tabular.html'
    fk_name = 'back_to_lexicalconceptualresourcetextinfotype_model'


# pylint: disable-msg=C0103
class languageDescriptionInfo_model_inline(SchemaModelInline):
    model = languageDescriptionInfoType_model


# pylint: disable-msg=C0103
class languageInfo_model_inline_corpusTextInfoType_model(SchemaModelInline):
    model = languageInfoType_model
    fk_name = 'back_to_corpustextinfotype_model'
    extra = 0
    min_num = 1


# pylint: disable-msg=C0103
class languageInfo_model_inline_languageDescriptionTextInfoType_model(SchemaModelInline):
    model = languageInfoType_model
    fk_name = 'back_to_languagedescriptiontextinfotype_model'
    extra = 0
    min_num = 1


# pylint: disable-msg=C0103
class languageInfo_model_inline_lexicalConceptualResourceTextInfoType_model(SchemaModelInline):
    model = languageInfoType_model
    fk_name = 'back_to_lexicalconceptualresourcetextinfotype_model'
    extra = 0
    min_num = 1


# pylint: disable-msg=C0103
class languageSetInfo_model_inline_inputInfoType_model(SchemaModelInline):
    model = languageSetInfoType_model
    collapse = True
    fk_name = 'back_to_inputinfotype_model'


# pylint: disable-msg=C0103
class languageSetInfo_model_inline_outputInfoType_model(SchemaModelInline):
    model = languageSetInfoType_model
    collapse = True
    fk_name = 'back_to_outputinfotype_model'


# pylint: disable-msg=C0103
class lexicalConceptualResourceInfo_model_inline(SchemaModelInline):
    model = lexicalConceptualResourceInfoType_model


# pylint: disable-msg=C0103
class organizationInfo_model_inline(SchemaModelInline):
    model = organizationInfoType_model


# pylint: disable-msg=C0103
class personInfo_model_inline(SchemaModelInline):
    model = personInfoType_model


# pylint: disable-msg=C0103
class relationInfo_model_inline(SchemaModelInline):
    form = RelationsForm
    model = relationInfoType_model
    collapse = False
    min_num = 1
    extra = 0


# pylint: disable-msg=C0103
class sizeInfo_model_inline_corpusTextInfoType_model(SchemaModelInline):
    model = sizeInfoType_model
    template = 'admin/edit_inline/tabular.html'
    fk_name = 'back_to_corpustextinfotype_model'


# pylint: disable-msg=C0103
class sizeInfo_model_inline_languageDescriptionTextInfoType_model(SchemaModelInline):
    model = sizeInfoType_model
    template = 'admin/edit_inline/tabular.html'
    fk_name = 'back_to_languagedescriptiontextinfotype_model'


# pylint: disable-msg=C0103
class sizeInfo_model_inline_lexicalConceptualResourceTextInfoType_model(SchemaModelInline):
    model = sizeInfoType_model
    template = 'admin/edit_inline/tabular.html'
    fk_name = 'back_to_lexicalconceptualresourcetextinfotype_model'


# pylint: disable-msg=C0103
class textClassificationInfo_model_inline_corpusTextInfoType_model(SchemaModelInline):
    model = textClassificationInfoType_model
    collapse = True
    fk_name = 'back_to_corpustextinfotype_model'


# pylint: disable-msg=C0103
class textClassificationInfo_model_inline_languageDescriptionTextInfoType_model(SchemaModelInline):
    model = textClassificationInfoType_model
    collapse = True
    fk_name = 'back_to_languagedescriptiontextinfotype_model'


# pylint: disable-msg=C0103
class textFormatInfo_model_inline_corpusTextInfoType_model(SchemaModelInline):
    model = textFormatInfoType_model
    template = 'admin/edit_inline/tabular.html'
    fk_name = 'back_to_corpustextinfotype_model'


# pylint: disable-msg=C0103
class textFormatInfo_model_inline_languageDescriptionTextInfoType_model(SchemaModelInline):
    model = textFormatInfoType_model
    template = 'admin/edit_inline/tabular.html'
    fk_name = 'back_to_languagedescriptiontextinfotype_model'


# pylint: disable-msg=C0103
class textFormatInfo_model_inline_lexicalConceptualResourceTextInfoType_model(SchemaModelInline):
    model = textFormatInfoType_model
    template = 'admin/edit_inline/tabular.html'
    fk_name = 'back_to_lexicalconceptualresourcetextinfotype_model'


# pylint: disable-msg=C0103
class toolServiceInfo_model_inline(SchemaModelInline):
    model = toolServiceInfoType_model


# pylint: disable-msg=C0103
class validationInfo_model_inline(SchemaModelInline):
    model = validationInfoType_model
    collapse = True


admin.site.register(actorInfoType_model, SchemaModelAdmin)
admin.site.register(annotationInfoType_model, SchemaModelAdmin)
admin.site.register(characterEncodingInfoType_model, SchemaModelAdmin)
admin.site.register(communicationInfoType_model, SchemaModelAdmin)
admin.site.register(corpusInfoType_model, SchemaModelAdmin)
admin.site.register(corpusMediaTypeType_model, SchemaModelAdmin)
admin.site.register(corpusTextInfoType_model, SchemaModelAdmin)
admin.site.register(creationInfoType_model, SchemaModelAdmin)
admin.site.register(dependenciesInfoType_model, SchemaModelAdmin)
admin.site.register(distributionInfoType_model, SchemaModelAdmin)
admin.site.register(documentInfoType_model, SchemaModelAdmin)
admin.site.register(documentationInfoType_model, SchemaModelAdmin)
admin.site.register(domainInfoType_model, SchemaModelAdmin)
admin.site.register(domainSetInfoType_model, SchemaModelAdmin)
admin.site.register(identificationInfoType_model, SchemaModelAdmin)
admin.site.register(inputInfoType_model, SchemaModelAdmin)
admin.site.register(languageDescriptionEncodingInfoType_model, SchemaModelAdmin)
admin.site.register(languageDescriptionInfoType_model, SchemaModelAdmin)
admin.site.register(languageDescriptionMediaTypeType_model, SchemaModelAdmin)
admin.site.register(languageDescriptionTextInfoType_model, SchemaModelAdmin)
admin.site.register(languageInfoType_model, SchemaModelAdmin)
admin.site.register(languageSetInfoType_model, SchemaModelAdmin)
admin.site.register(languageVarietyInfoType_model, SchemaModelAdmin)
admin.site.register(lexicalConceptualResourceEncodingInfoType_model, SchemaModelAdmin)
admin.site.register(lexicalConceptualResourceInfoType_model, SchemaModelAdmin)
admin.site.register(lexicalConceptualResourceMediaTypeType_model, SchemaModelAdmin)
admin.site.register(lexicalConceptualResourceTextInfoType_model, SchemaModelAdmin)
admin.site.register(licenceInfoType_model, SchemaModelAdmin)
admin.site.register(lingualityInfoType_model, SchemaModelAdmin)
admin.site.register(metadataInfoType_model, SchemaModelAdmin)
admin.site.register(organizationInfoType_model, SchemaModelAdmin)
admin.site.register(outputInfoType_model, SchemaModelAdmin)
admin.site.register(personInfoType_model, SchemaModelAdmin)
admin.site.register(projectInfoType_model, SchemaModelAdmin)
admin.site.register(relationInfoType_model, SchemaModelAdmin)
admin.site.register(resourceComponentTypeType_model, SchemaModelAdmin)
admin.site.register(resourceCreationInfoType_model, SchemaModelAdmin)
admin.site.register(resourceDocumentationInfoType_model, SchemaModelAdmin)
admin.site.register(resourceInfoType_model, SchemaModelAdmin)
admin.site.register(sizeInfoType_model, SchemaModelAdmin)
admin.site.register(targetResourceInfoType_model, SchemaModelAdmin)
admin.site.register(textClassificationInfoType_model, SchemaModelAdmin)
admin.site.register(textFormatInfoType_model, SchemaModelAdmin)
admin.site.register(toolServiceCreationInfoType_model, SchemaModelAdmin)
admin.site.register(toolServiceEvaluationInfoType_model, SchemaModelAdmin)
admin.site.register(toolServiceInfoType_model, SchemaModelAdmin)
admin.site.register(toolServiceOperationInfoType_model, SchemaModelAdmin)
admin.site.register(validationInfoType_model, SchemaModelAdmin)
admin.site.register(versionInfoType_model, SchemaModelAdmin)

from metashare.repository.editor import manual_admin_registration

manual_admin_registration.register()
