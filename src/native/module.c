#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <holder/holder.h>

#include <string.h>

#ifndef HOLDER_HAS_PROJECT_IMPORT
#define HOLDER_HAS_PROJECT_IMPORT 0
#endif

#ifndef HOLDER_HAS_CARD_COLLECTION_PAGE
#define HOLDER_HAS_CARD_COLLECTION_PAGE 0
#endif

#ifndef PyCFunction_CAST
#define PyCFunction_CAST(function) ((PyCFunction)(void (*)(void))(function))
#endif

typedef struct {
    PyObject *holder_error;
} holder_module_state;

typedef struct {
    PyObject_HEAD
    holder_context *context;
} ContextObject;

static holder_module_state *
get_module_state_from_context(ContextObject *self)
{
    PyObject *module = PyType_GetModule(Py_TYPE(self));
    if (module == NULL) {
        return NULL;
    }
    return PyModule_GetState(module);
}

static int
raise_holder_error(ContextObject *self, int result, holder_error *error)
{
    const char *message = error != NULL ? holder_error_message(error) : "libholder operation failed";

    if (result == HOLDER_ERROR_ALLOCATION) {
        holder_error_destroy(error);
        PyErr_NoMemory();
        return -1;
    }

    PyObject *exception = PyExc_RuntimeError;
    if (result == HOLDER_ERROR_INVALID_ARGUMENT) {
        exception = PyExc_ValueError;
    } else {
        holder_module_state *state = get_module_state_from_context(self);
        if (state == NULL) {
            holder_error_destroy(error);
            return -1;
        }
        exception = state->holder_error;
    }

    PyErr_SetString(exception, message);
    holder_error_destroy(error);
    return -1;
}

static int
ensure_context_open(ContextObject *self)
{
    if (self->context == NULL) {
        PyErr_SetString(PyExc_RuntimeError, "Holder context is closed");
        return 0;
    }
    return 1;
}

static PyObject *
json_from_native_string(char *value)
{
    if (value == NULL) {
        PyErr_SetString(PyExc_RuntimeError, "libholder returned no JSON result");
        return NULL;
    }

    PyObject *text = PyUnicode_DecodeUTF8(value, (Py_ssize_t)strlen(value), "strict");
    holder_string_free(value);
    if (text == NULL) {
        return NULL;
    }

    PyObject *json_module = PyImport_ImportModule("json");
    if (json_module == NULL) {
        Py_DECREF(text);
        return NULL;
    }

    PyObject *loads = PyObject_GetAttrString(json_module, "loads");
    Py_DECREF(json_module);
    if (loads == NULL) {
        Py_DECREF(text);
        return NULL;
    }

    PyObject *result = PyObject_CallOneArg(loads, text);
    Py_DECREF(loads);
    Py_DECREF(text);
    return result;
}

static PyObject *
unicode_from_native_string(char *value)
{
    if (value == NULL) {
        PyErr_SetString(PyExc_RuntimeError, "libholder returned no string result");
        return NULL;
    }

    PyObject *result = PyUnicode_DecodeUTF8(value, (Py_ssize_t)strlen(value), "strict");
    holder_string_free(value);
    return result;
}

static int
Context_init(ContextObject *self, PyObject *args, PyObject *kwargs)
{
    const char *data_dir = NULL;
    const char *schema_sql = NULL;
    static char *keywords[] = {"data_dir", "schema_sql", NULL};

    if (!PyArg_ParseTupleAndKeywords(
            args,
            kwargs,
            "ss:Context",
            keywords,
            &data_dir,
            &schema_sql)) {
        return -1;
    }

    holder_context *new_context = NULL;
    holder_error *error = NULL;
    const int result = holder_context_open(data_dir, schema_sql, &new_context, &error);
    if (result != HOLDER_OK) {
        return raise_holder_error(self, result, error);
    }
    holder_error_destroy(error);

    holder_context *old_context = self->context;
    self->context = new_context;
    holder_context_destroy(old_context);
    return 0;
}

static void
Context_dealloc(ContextObject *self)
{
    holder_context_destroy(self->context);
    self->context = NULL;
    Py_TYPE(self)->tp_free((PyObject *)self);
}

static PyObject *
Context_close(ContextObject *self, PyObject *Py_UNUSED(ignored))
{
    holder_context *context = self->context;
    self->context = NULL;
    holder_context_destroy(context);
    Py_RETURN_NONE;
}

static PyObject *
Context_enter(ContextObject *self, PyObject *Py_UNUSED(ignored))
{
    if (!ensure_context_open(self)) {
        return NULL;
    }
    return Py_NewRef(self);
}

static PyObject *
Context_exit(ContextObject *self, PyObject *Py_UNUSED(args))
{
    return Context_close(self, NULL);
}

static PyObject *
Context_create_project(ContextObject *self, PyObject *args, PyObject *kwargs)
{
    const char *name = NULL;
    static char *keywords[] = {"name", NULL};

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "s:create_project", keywords, &name)) {
        return NULL;
    }
    if (!ensure_context_open(self)) {
        return NULL;
    }

    char *output = NULL;
    holder_error *error = NULL;
    const int result = holder_project_create(
        self->context,
        name,
        NULL,
        NULL,
        &output,
        &error
    );
    if (result != HOLDER_OK) {
        holder_string_free(output);
        raise_holder_error(self, result, error);
        return NULL;
    }
    holder_error_destroy(error);
    return json_from_native_string(output);
}

static PyObject *
Context_list_projects(ContextObject *self, PyObject *Py_UNUSED(ignored))
{
    if (!ensure_context_open(self)) {
        return NULL;
    }

    char *output = NULL;
    holder_error *error = NULL;
    const int result = holder_project_list(self->context, &output, &error);
    if (result != HOLDER_OK) {
        holder_string_free(output);
        raise_holder_error(self, result, error);
        return NULL;
    }
    holder_error_destroy(error);
    return json_from_native_string(output);
}

static PyObject *
Context_create_card(ContextObject *self, PyObject *args, PyObject *kwargs)
{
    const char *project_id = NULL;
    const char *title = NULL;
    const char *content = NULL;
    const char *parent_card_id = NULL;
    static char *keywords[] = {
        "project_id", "title", "content", "parent_card_id", NULL
    };

    if (!PyArg_ParseTupleAndKeywords(
            args,
            kwargs,
            "ss|zz:create_card",
            keywords,
            &project_id,
            &title,
            &content,
            &parent_card_id)) {
        return NULL;
    }
    if (!ensure_context_open(self)) {
        return NULL;
    }

    char *output = NULL;
    holder_error *error = NULL;
    const int result = holder_card_create(
        self->context,
        project_id,
        title,
        content,
        parent_card_id,
        &output,
        &error
    );
    if (result != HOLDER_OK) {
        holder_string_free(output);
        raise_holder_error(self, result, error);
        return NULL;
    }
    holder_error_destroy(error);
    return json_from_native_string(output);
}

static PyObject *
Context_list_links(ContextObject *self, PyObject *args, PyObject *kwargs)
{
    const char *card_id = NULL;
    static char *keywords[] = {"card_id", NULL};
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "s:list_links", keywords, &card_id)) {
        return NULL;
    }
    if (!ensure_context_open(self)) {
        return NULL;
    }
    char *output = NULL;
    holder_error *error = NULL;
    const int result = holder_card_list_links(self->context, card_id, &output, &error);
    if (result != HOLDER_OK) {
        holder_string_free(output);
        raise_holder_error(self, result, error);
        return NULL;
    }
    holder_error_destroy(error);
    return json_from_native_string(output);
}

typedef int (*context_json_operation)(holder_context *, const char *, char **, holder_error **);

static PyObject *
context_json_read(ContextObject *self, PyObject *args, PyObject *kwargs,
                  const char *argument, context_json_operation operation)
{
    const char *id = NULL;
    char *keywords[] = {(char *)argument, NULL};
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "s", keywords, &id) ||
        !ensure_context_open(self)) {
        return NULL;
    }
    char *output = NULL;
    holder_error *error = NULL;
    const int result = operation(self->context, id, &output, &error);
    if (result != HOLDER_OK) {
        holder_string_free(output);
        raise_holder_error(self, result, error);
        return NULL;
    }
    holder_error_destroy(error);
    return json_from_native_string(output);
}

static PyObject *
Context_resolve_card(ContextObject *self, PyObject *args, PyObject *kwargs)
{
    const char *project_id = NULL;
    const char *card_id = NULL;
    static char *keywords[] = {"project_id", "card_id", NULL};
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "ss:resolve_card", keywords,
                                    &project_id, &card_id) || !ensure_context_open(self)) {
        return NULL;
    }
    char *output = NULL;
    holder_error *error = NULL;
    const int result = holder_card_reference_resolve(
        self->context, project_id, card_id, 2, &output, &error
    );
    if (result != HOLDER_OK) {
        holder_string_free(output);
        raise_holder_error(self, result, error);
        return NULL;
    }
    holder_error_destroy(error);
    return json_from_native_string(output);
}

static PyObject *
Context_move_card(ContextObject *self, PyObject *args, PyObject *kwargs)
{
    const char *project_id = NULL;
    const char *card_id = NULL;
    const char *request_json = NULL;
    static char *keywords[] = {"project_id", "card_id", "request_json", NULL};
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "sss:move_card", keywords,
                                    &project_id, &card_id, &request_json) ||
        !ensure_context_open(self)) {
        return NULL;
    }
    char *output = NULL;
    holder_error *error = NULL;
    const int result = holder_card_move_json(
        self->context, project_id, card_id, request_json, &output, &error
    );
    if (result != HOLDER_OK) {
        holder_string_free(output);
        raise_holder_error(self, result, error);
        return NULL;
    }
    holder_error_destroy(error);
    return json_from_native_string(output);
}

static PyObject *
Context_list_trashed_cards(ContextObject *self, PyObject *args, PyObject *kwargs)
{
    return context_json_read(self, args, kwargs, "project_id", holder_card_list_trashed);
}

static PyObject *
Context_restore_card(ContextObject *self, PyObject *args, PyObject *kwargs)
{
    return context_json_read(self, args, kwargs, "card_id", holder_card_restore);
}

typedef int (*context_card_mutation)(holder_context *, const char *, holder_error **);

static PyObject *
context_mutate_card(ContextObject *self, PyObject *args, PyObject *kwargs,
                    context_card_mutation operation)
{
    const char *card_id = NULL;
    static char *keywords[] = {"card_id", NULL};
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "s", keywords, &card_id) ||
        !ensure_context_open(self)) {
        return NULL;
    }
    holder_error *error = NULL;
    const int result = operation(self->context, card_id, &error);
    if (result != HOLDER_OK) {
        raise_holder_error(self, result, error);
        return NULL;
    }
    holder_error_destroy(error);
    Py_RETURN_NONE;
}

static PyObject *
Context_trash_card(ContextObject *self, PyObject *args, PyObject *kwargs)
{
    return context_mutate_card(self, args, kwargs, holder_card_delete);
}

static PyObject *
Context_purge_card(ContextObject *self, PyObject *args, PyObject *kwargs)
{
    return context_mutate_card(self, args, kwargs, holder_card_purge);
}

static PyObject *
Context_list_tags(ContextObject *self, PyObject *args, PyObject *kwargs)
{
    return context_json_read(self, args, kwargs, "card_id", holder_card_list_tags);
}

static PyObject *
Context_import_project(ContextObject *self, PyObject *args, PyObject *kwargs)
{
#if HOLDER_HAS_PROJECT_IMPORT
    return context_json_read(self, args, kwargs, "project_root", holder_project_import);
#else
    (void)self;
    (void)args;
    (void)kwargs;
    PyErr_SetString(PyExc_NotImplementedError,
        "This core build does not support explicit project import");
    return NULL;
#endif
}

static PyObject *
Context_list_editable_tags(ContextObject *self, PyObject *args, PyObject *kwargs)
{
    return context_json_read(self, args, kwargs, "card_id", holder_card_list_editable_tags);
}

static PyObject *
Context_list_project_tags(ContextObject *self, PyObject *args, PyObject *kwargs)
{
    return context_json_read(self, args, kwargs, "project_id", holder_project_list_tags);
}

static PyObject *
Context_list_milestones(ContextObject *self, PyObject *args, PyObject *kwargs)
{
    return context_json_read(self, args, kwargs, "card_id", holder_card_list_milestones);
}

static int
epoch_seconds(PyObject *value, long long *output)
{
    if (!PyLong_Check(value) || PyBool_Check(value)) {
        PyErr_SetString(PyExc_TypeError, "timestamp must be an integer Unix second");
        return 0;
    }
    *output = PyLong_AsLongLong(value);
    return !PyErr_Occurred();
}

static PyObject *
Context_add_milestone(ContextObject *self, PyObject *args, PyObject *kwargs)
{
    const char *card_id = NULL;
    PyObject *start_object = NULL;
    PyObject *end_object = Py_None;
    PyObject *all_day = Py_False;
    const char *kind = NULL;
    const char *description = NULL;
    static char *keywords[] = {"card_id", "start_at", "end_at", "all_day", "kind", "description", NULL};
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "sO|OOzz:add_milestone", keywords,
                                    &card_id, &start_object, &end_object, &all_day, &kind, &description) ||
        !ensure_context_open(self)) {
        return NULL;
    }
    long long start_at = 0;
    long long end_at = 0;
    if (!epoch_seconds(start_object, &start_at) ||
        (end_object != Py_None && !epoch_seconds(end_object, &end_at))) {
        return NULL;
    }
    if (!PyBool_Check(all_day)) {
        PyErr_SetString(PyExc_TypeError, "all_day must be bool");
        return NULL;
    }
    char *output = NULL;
    holder_error *error = NULL;
    const int result = holder_card_milestone_add(self->context, card_id, start_at,
        end_object != Py_None, end_at, all_day == Py_True, kind, description, &output, &error);
    if (result != HOLDER_OK) {
        holder_string_free(output);
        raise_holder_error(self, result, error);
        return NULL;
    }
    holder_error_destroy(error);
    return json_from_native_string(output);
}

static PyObject *
Context_update_milestone(ContextObject *self, PyObject *args, PyObject *kwargs)
{
    const char *project_id = NULL;
    const char *card_id = NULL;
    const char *milestone_id = NULL;
    const char *update_json = NULL;
    static char *keywords[] = {"project_id", "card_id", "milestone_id", "update_json", NULL};
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "ssss:update_milestone", keywords,
                                    &project_id, &card_id, &milestone_id, &update_json) ||
        !ensure_context_open(self)) {
        return NULL;
    }
    char *output = NULL;
    holder_error *error = NULL;
    const int result = holder_card_milestone_update_json(self->context, project_id,
        card_id, milestone_id, update_json, &output, &error);
    if (result != HOLDER_OK) {
        holder_string_free(output);
        raise_holder_error(self, result, error);
        return NULL;
    }
    holder_error_destroy(error);
    return json_from_native_string(output);
}

static PyObject *
Context_remove_milestone(ContextObject *self, PyObject *args, PyObject *kwargs)
{
    const char *card_id = NULL;
    const char *milestone_id = NULL;
    static char *keywords[] = {"card_id", "milestone_id", NULL};
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "ss:remove_milestone", keywords,
                                    &card_id, &milestone_id) || !ensure_context_open(self)) {
        return NULL;
    }
    holder_error *error = NULL;
    const int result = holder_card_milestone_remove(self->context, card_id, milestone_id, &error);
    if (result != HOLDER_OK) {
        raise_holder_error(self, result, error);
        return NULL;
    }
    holder_error_destroy(error);
    Py_RETURN_NONE;
}

static PyObject *
Context_milestones_in_range(ContextObject *self, PyObject *args, PyObject *kwargs)
{
    const char *project_id = NULL;
    PyObject *from_object = NULL;
    PyObject *to_object = NULL;
    static char *keywords[] = {"project_id", "from_at", "to_at", NULL};
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "sOO:milestones_in_range", keywords,
                                    &project_id, &from_object, &to_object) || !ensure_context_open(self)) {
        return NULL;
    }
    long long from_at = 0;
    long long to_at = 0;
    if (!epoch_seconds(from_object, &from_at) || !epoch_seconds(to_object, &to_at)) {
        return NULL;
    }
    char *output = NULL;
    holder_error *error = NULL;
    const int result = holder_project_list_milestones_in_range(self->context, project_id,
        from_at, to_at, &output, &error);
    if (result != HOLDER_OK) {
        holder_string_free(output);
        raise_holder_error(self, result, error);
        return NULL;
    }
    holder_error_destroy(error);
    return json_from_native_string(output);
}

typedef int (*tag_mutation)(holder_context *, const char *, const char *, int *, holder_error **);

static PyObject *
mutate_tag(ContextObject *self, PyObject *args, PyObject *kwargs, tag_mutation operation)
{
    const char *card_id = NULL;
    const char *tag = NULL;
    static char *keywords[] = {"card_id", "tag", NULL};
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "ss", keywords, &card_id, &tag) ||
        !ensure_context_open(self)) {
        return NULL;
    }
    int status = 0;
    holder_error *error = NULL;
    const int result = operation(self->context, card_id, tag, &status, &error);
    if (result != HOLDER_OK) {
        raise_holder_error(self, result, error);
        return NULL;
    }
    holder_error_destroy(error);
    return PyLong_FromLong(status);
}

static PyObject *
Context_add_tag(ContextObject *self, PyObject *args, PyObject *kwargs)
{
    return mutate_tag(self, args, kwargs, holder_card_tag_add);
}

static PyObject *
Context_remove_tag(ContextObject *self, PyObject *args, PyObject *kwargs)
{
    return mutate_tag(self, args, kwargs, holder_card_tag_remove);
}

static PyObject *
Context_cards_with_tag(ContextObject *self, PyObject *args, PyObject *kwargs)
{
    const char *project_id = NULL;
    const char *tag = NULL;
    static char *keywords[] = {"project_id", "tag", NULL};
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "ss:cards_with_tag", keywords,
                                    &project_id, &tag) || !ensure_context_open(self)) {
        return NULL;
    }
    char *output = NULL;
    holder_error *error = NULL;
    const int result = holder_cards_with_tag(self->context, project_id, tag, &output, &error);
    if (result != HOLDER_OK) {
        holder_string_free(output);
        raise_holder_error(self, result, error);
        return NULL;
    }
    holder_error_destroy(error);
    return json_from_native_string(output);
}

static PyObject *
Context_add_link(ContextObject *self, PyObject *args, PyObject *kwargs)
{
    const char *from_card_id = NULL;
    const char *to_card_id = NULL;
    const char *kind = NULL;
    const char *label = NULL;
    static char *keywords[] = {"from_card_id", "to_card_id", "kind", "label", NULL};
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "sss|z:add_link", keywords,
                                    &from_card_id, &to_card_id, &kind, &label)) {
        return NULL;
    }
    if (!ensure_context_open(self)) {
        return NULL;
    }
    char *output = NULL;
    holder_error *error = NULL;
    const int result = holder_card_link_add(
        self->context, from_card_id, to_card_id, kind, label, &output, &error);
    if (result != HOLDER_OK) {
        holder_string_free(output);
        raise_holder_error(self, result, error);
        return NULL;
    }
    holder_error_destroy(error);
    return json_from_native_string(output);
}

static PyObject *
Context_remove_link(ContextObject *self, PyObject *args, PyObject *kwargs)
{
    const char *from_card_id = NULL;
    const char *to_card_id = NULL;
    const char *kind = NULL;
    static char *keywords[] = {"from_card_id", "to_card_id", "kind", NULL};
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "sss:remove_link", keywords,
                                    &from_card_id, &to_card_id, &kind)) {
        return NULL;
    }
    if (!ensure_context_open(self)) {
        return NULL;
    }
    holder_error *error = NULL;
    const int result = holder_card_link_remove(
        self->context, from_card_id, to_card_id, kind, &error);
    if (result != HOLDER_OK) {
        raise_holder_error(self, result, error);
        return NULL;
    }
    holder_error_destroy(error);
    Py_RETURN_NONE;
}

static PyObject *
Context_list_cards(ContextObject *self, PyObject *args, PyObject *kwargs)
{
    const char *project_id = NULL;
    static char *keywords[] = {"project_id", NULL};

    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "s:list_cards", keywords, &project_id)) {
        return NULL;
    }
    if (!ensure_context_open(self)) {
        return NULL;
    }

    char *output = NULL;
    holder_error *error = NULL;
    const int result = holder_card_list(self->context, project_id, &output, &error);
    if (result != HOLDER_OK) {
        holder_string_free(output);
        raise_holder_error(self, result, error);
        return NULL;
    }
    holder_error_destroy(error);
    return json_from_native_string(output);
}

static PyObject *
Context_query_cards(ContextObject *self, PyObject *args, PyObject *kwargs)
{
    const char *project_id = NULL;
    const char *request_json = NULL;
    static char *keywords[] = {"project_id", "request_json", NULL};
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "ss:query_cards", keywords,
                                    &project_id, &request_json)) {
        return NULL;
    }
    if (!ensure_context_open(self)) {
        return NULL;
    }
    char *output = NULL;
    holder_error *error = NULL;
    const int result = holder_card_query_json(
        self->context, project_id, request_json, &output, &error
    );
    if (result != HOLDER_OK) {
        holder_string_free(output);
        raise_holder_error(self, result, error);
        return NULL;
    }
    holder_error_destroy(error);
    return json_from_native_string(output);
}

static PyObject *
Context_collection_cards_page(ContextObject *self, PyObject *args, PyObject *kwargs)
{
    const char *project_id = NULL;
    const char *request_json = NULL;
    static char *keywords[] = {"project_id", "request_json", NULL};
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "ss:collection_cards_page", keywords,
                                    &project_id, &request_json)) {
        return NULL;
    }
    if (!ensure_context_open(self)) {
        return NULL;
    }
#if HOLDER_HAS_CARD_COLLECTION_PAGE
    char *output = NULL;
    holder_error *error = NULL;
    const int result = holder_card_collection_page_json(
        self->context, project_id, request_json, &output, &error
    );
    if (result != HOLDER_OK) {
        holder_string_free(output);
        raise_holder_error(self, result, error);
        return NULL;
    }
    holder_error_destroy(error);
    return json_from_native_string(output);
#else
    PyErr_SetString(PyExc_NotImplementedError,
                    "Filtered card batches require a Core SDK with collection pagination support");
    return NULL;
#endif
}

static PyObject *
Context_list_complete_cards_page(ContextObject *self, PyObject *args, PyObject *kwargs)
{
    const char *project_id = NULL;
    const char *cursor = NULL;
    int limit = 256;
    static char *keywords[] = {"project_id", "cursor", "limit", NULL};

    if (!PyArg_ParseTupleAndKeywords(
            args,
            kwargs,
            "s|zi:list_complete_cards_page",
            keywords,
            &project_id,
            &cursor,
            &limit)) {
        return NULL;
    }
    if (!ensure_context_open(self)) {
        return NULL;
    }

    char *output = NULL;
    holder_error *error = NULL;
    const int result = holder_card_list_complete_page(
        self->context,
        project_id,
        cursor,
        limit,
        &output,
        &error
    );
    if (result != HOLDER_OK) {
        holder_string_free(output);
        raise_holder_error(self, result, error);
        return NULL;
    }
    holder_error_destroy(error);
    return json_from_native_string(output);
}

static PyObject *
Context_get_card_content(ContextObject *self, PyObject *args, PyObject *kwargs)
{
    const char *card_id = NULL;
    static char *keywords[] = {"card_id", NULL};

    if (!PyArg_ParseTupleAndKeywords(
            args,
            kwargs,
            "s:get_card_content",
            keywords,
            &card_id)) {
        return NULL;
    }
    if (!ensure_context_open(self)) {
        return NULL;
    }

    char *output = NULL;
    holder_error *error = NULL;
    const int result = holder_card_get_content(self->context, card_id, &output, &error);
    if (result != HOLDER_OK) {
        holder_string_free(output);
        raise_holder_error(self, result, error);
        return NULL;
    }
    holder_error_destroy(error);
    return unicode_from_native_string(output);
}

static PyObject *
Context_update_card(ContextObject *self, PyObject *args, PyObject *kwargs)
{
    const char *card_id = NULL;
    const char *content = NULL;
    const char *title = NULL;
    static char *keywords[] = {"card_id", "content", "title", NULL};

    if (!PyArg_ParseTupleAndKeywords(
            args,
            kwargs,
            "ss|z:update_card",
            keywords,
            &card_id,
            &content,
            &title)) {
        return NULL;
    }
    if (!ensure_context_open(self)) {
        return NULL;
    }

    char *output = NULL;
    holder_error *error = NULL;
    const int result = holder_card_update_content(
        self->context,
        card_id,
        content,
        title,
        &output,
        &error
    );
    if (result != HOLDER_OK) {
        holder_string_free(output);
        raise_holder_error(self, result, error);
        return NULL;
    }
    holder_error_destroy(error);
    return json_from_native_string(output);
}

static PyObject *
Context_get_closed(ContextObject *self, void *Py_UNUSED(closure))
{
    return PyBool_FromLong(self->context == NULL);
}

PyDoc_STRVAR(
    Context_doc,
    "Context(data_dir, schema_sql)\n--\n\n"
    "Own an embedded libholder context. Prefer holderkit.Context in public code."
);

static PyMethodDef Context_methods[] = {
    {"import_project", PyCFunction_CAST(Context_import_project), METH_VARARGS | METH_KEYWORDS,
     PyDoc_STR("Import a durable plain project into an empty context database.")},
    {"list_milestones", PyCFunction_CAST(Context_list_milestones), METH_VARARGS | METH_KEYWORDS,
     PyDoc_STR("List a card's milestones ordered by start time.")},
    {"add_milestone", PyCFunction_CAST(Context_add_milestone), METH_VARARGS | METH_KEYWORDS,
     PyDoc_STR("Add a milestone and return the updated milestone list.")},
    {"update_milestone", PyCFunction_CAST(Context_update_milestone), METH_VARARGS | METH_KEYWORDS,
     PyDoc_STR("Partially update an owned milestone using core's JSON contract.")},
    {"remove_milestone", PyCFunction_CAST(Context_remove_milestone), METH_VARARGS | METH_KEYWORDS,
     PyDoc_STR("Remove a milestone if it belongs to the given card.")},
    {"milestones_in_range", PyCFunction_CAST(Context_milestones_in_range), METH_VARARGS | METH_KEYWORDS,
     PyDoc_STR("List live project milestones starting in an inclusive time range.")},
    {"list_tags", PyCFunction_CAST(Context_list_tags), METH_VARARGS | METH_KEYWORDS,
     PyDoc_STR("List a card's normalized tags.")},
    {"list_editable_tags", PyCFunction_CAST(Context_list_editable_tags), METH_VARARGS | METH_KEYWORDS,
     PyDoc_STR("List tags on a card's editable trailing tag line.")},
    {"list_project_tags", PyCFunction_CAST(Context_list_project_tags), METH_VARARGS | METH_KEYWORDS,
     PyDoc_STR("List project tags and live-card counts.")},
    {"cards_with_tag", PyCFunction_CAST(Context_cards_with_tag), METH_VARARGS | METH_KEYWORDS,
     PyDoc_STR("Find live cards carrying a tag in a project.")},
    {"add_tag", PyCFunction_CAST(Context_add_tag), METH_VARARGS | METH_KEYWORDS,
     PyDoc_STR("Semantically add a tag and return core's status.")},
    {"remove_tag", PyCFunction_CAST(Context_remove_tag), METH_VARARGS | METH_KEYWORDS,
     PyDoc_STR("Remove a trailing tag and return core's status.")},
    {"list_links", PyCFunction_CAST(Context_list_links),
     METH_VARARGS | METH_KEYWORDS, PyDoc_STR("Read a card's connections and hierarchy.")},
    {"add_link", PyCFunction_CAST(Context_add_link),
     METH_VARARGS | METH_KEYWORDS, PyDoc_STR("Add or update an explicit card connection.")},
    {"remove_link", PyCFunction_CAST(Context_remove_link),
     METH_VARARGS | METH_KEYWORDS, PyDoc_STR("Remove an explicit card connection.")},
    {"close", (PyCFunction)Context_close, METH_NOARGS,
     PyDoc_STR("Release the native Holder context. Safe to call repeatedly.")},
    {"__enter__", (PyCFunction)Context_enter, METH_NOARGS, NULL},
    {"__exit__", (PyCFunction)Context_exit, METH_VARARGS, NULL},
    {"create_project", PyCFunction_CAST(Context_create_project),
     METH_VARARGS | METH_KEYWORDS, PyDoc_STR("Create a plain Holder project.")},
    {"list_projects", (PyCFunction)Context_list_projects, METH_NOARGS,
     PyDoc_STR("List Holder projects.")},
    {"create_card", PyCFunction_CAST(Context_create_card),
     METH_VARARGS | METH_KEYWORDS, PyDoc_STR("Create a card and return its metadata.")},
    {"list_cards", PyCFunction_CAST(Context_list_cards),
     METH_VARARGS | METH_KEYWORDS, PyDoc_STR("List live cards in a project.")},
    {"resolve_card", PyCFunction_CAST(Context_resolve_card),
     METH_VARARGS | METH_KEYWORDS, PyDoc_STR("Resolve a live or trashed card through Core.")},
    {"move_card", PyCFunction_CAST(Context_move_card),
     METH_VARARGS | METH_KEYWORDS, PyDoc_STR("Move a card using Core's placement rules.")},
    {"list_trashed_cards", PyCFunction_CAST(Context_list_trashed_cards),
     METH_VARARGS | METH_KEYWORDS, PyDoc_STR("List trashed card metadata in a project.")},
    {"trash_card", PyCFunction_CAST(Context_trash_card),
     METH_VARARGS | METH_KEYWORDS, PyDoc_STR("Move a card to Trash and promote its live children.")},
    {"restore_card", PyCFunction_CAST(Context_restore_card),
     METH_VARARGS | METH_KEYWORDS, PyDoc_STR("Restore one trashed card through Core.")},
    {"purge_card", PyCFunction_CAST(Context_purge_card),
     METH_VARARGS | METH_KEYWORDS, PyDoc_STR("Permanently remove a card that is already in Trash.")},
    {"query_cards", PyCFunction_CAST(Context_query_cards),
     METH_VARARGS | METH_KEYWORDS, PyDoc_STR("Query a card metadata view through Core.")},
    {"collection_cards_page", PyCFunction_CAST(Context_collection_cards_page),
     METH_VARARGS | METH_KEYWORDS, PyDoc_STR("Read a filtered card collection page through Core.")},
    {"list_complete_cards_page", PyCFunction_CAST(Context_list_complete_cards_page),
     METH_VARARGS | METH_KEYWORDS,
     PyDoc_STR("List one opaque-cursor page of live cards with authoritative bodies.")},
    {"get_card_content", PyCFunction_CAST(Context_get_card_content),
     METH_VARARGS | METH_KEYWORDS, PyDoc_STR("Return a card's Markdown body.")},
    {"update_card", PyCFunction_CAST(Context_update_card),
     METH_VARARGS | METH_KEYWORDS, PyDoc_STR("Replace a card's content and optionally title.")},
    {NULL, NULL, 0, NULL}
};

static PyGetSetDef Context_getset[] = {
    {"closed", (getter)Context_get_closed, NULL,
     PyDoc_STR("Whether the native context has been released."), NULL},
    {NULL, NULL, NULL, NULL, NULL}
};

static PyType_Slot Context_slots[] = {
    {Py_tp_doc, (void *)Context_doc},
    {Py_tp_dealloc, (void *)Context_dealloc},
    {Py_tp_init, (void *)Context_init},
    {Py_tp_new, (void *)PyType_GenericNew},
    {Py_tp_methods, Context_methods},
    {Py_tp_getset, Context_getset},
    {0, NULL}
};

static PyType_Spec Context_spec = {
    .name = "holderkit._native.Context",
    .basicsize = sizeof(ContextObject),
    .itemsize = 0,
    .flags = Py_TPFLAGS_DEFAULT,
    .slots = Context_slots,
};

static int
holder_module_traverse(PyObject *module, visitproc visit, void *arg)
{
    holder_module_state *state = PyModule_GetState(module);
    Py_VISIT(state->holder_error);
    return 0;
}

static int
holder_module_clear(PyObject *module)
{
    holder_module_state *state = PyModule_GetState(module);
    Py_CLEAR(state->holder_error);
    return 0;
}

static int
holder_module_exec(PyObject *module)
{
    if (PyModule_AddIntConstant(module, "PROJECT_IMPORT_SUPPORTED", HOLDER_HAS_PROJECT_IMPORT) < 0) {
        return -1;
    }
    if (PyModule_AddIntConstant(module, "CARD_COLLECTION_SUPPORTED", HOLDER_HAS_CARD_COLLECTION_PAGE) < 0) {
        return -1;
    }
    if (PyModule_AddIntConstant(module, "CARD_PAGE_MAX_LIMIT", HOLDER_CARD_LIST_COMPLETE_MAX_LIMIT) < 0) {
        return -1;
    }
    holder_module_state *state = PyModule_GetState(module);
    state->holder_error = PyErr_NewException(
        "holderkit._native.HolderError",
        PyExc_RuntimeError,
        NULL
    );
    if (state->holder_error == NULL) {
        return -1;
    }
    if (PyModule_AddObjectRef(module, "HolderError", state->holder_error) < 0) {
        return -1;
    }

    PyObject *context_type = PyType_FromModuleAndSpec(module, &Context_spec, NULL);
    if (context_type == NULL) {
        return -1;
    }
    if (PyModule_AddObject(module, "Context", context_type) < 0) {
        Py_DECREF(context_type);
        return -1;
    }
    return 0;
}

static PyModuleDef_Slot holder_module_slots[] = {
    {Py_mod_exec, holder_module_exec},
    {0, NULL}
};

static struct PyModuleDef holder_module = {
    PyModuleDef_HEAD_INIT,
    .m_name = "holderkit._native",
    .m_doc = "Native CPython bindings for embedded libholder.",
    .m_size = sizeof(holder_module_state),
    .m_methods = NULL,
    .m_slots = holder_module_slots,
    .m_traverse = holder_module_traverse,
    .m_clear = holder_module_clear,
    .m_free = NULL,
};

PyMODINIT_FUNC
PyInit__native(void)
{
    return PyModuleDef_Init(&holder_module);
}
