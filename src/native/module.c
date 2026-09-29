#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <holder/holder.h>

#include <string.h>

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
    "Own an embedded libholder context. Prefer holder.Context in public code."
);

static PyMethodDef Context_methods[] = {
    {"close", (PyCFunction)Context_close, METH_NOARGS,
     PyDoc_STR("Release the native Holder context. Safe to call repeatedly.")},
    {"__enter__", (PyCFunction)Context_enter, METH_NOARGS, NULL},
    {"__exit__", (PyCFunction)Context_exit, METH_VARARGS, NULL},
    {"create_project", PyCFunction_CAST(Context_create_project),
     METH_VARARGS | METH_KEYWORDS, PyDoc_STR("Create a plain Holder project.")},
    {"create_card", PyCFunction_CAST(Context_create_card),
     METH_VARARGS | METH_KEYWORDS, PyDoc_STR("Create a card and return its metadata.")},
    {"list_cards", PyCFunction_CAST(Context_list_cards),
     METH_VARARGS | METH_KEYWORDS, PyDoc_STR("List live cards in a project.")},
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
    .name = "holder._native.Context",
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
    holder_module_state *state = PyModule_GetState(module);
    state->holder_error = PyErr_NewException(
        "holder._native.HolderError",
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
    .m_name = "holder._native",
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
