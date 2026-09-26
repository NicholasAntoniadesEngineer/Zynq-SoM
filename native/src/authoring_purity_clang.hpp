#pragma once

// Small private ABI bridge to the public, ABI-stable libclang C interface.
// Layouts/signatures: https://clang.llvm.org/doxygen/Index_8h_source.html,
// CXSourceLocation.h and CXString.h. Deliberately no Clang C++ API, subprocess
// JSON scraping, or dependency on a particular compiler's AST text format.
// Enum values used here are documented C API values, not AST implementation IDs.
// No public header leaks these types. Missing symbols are fatal, never a waiver.
#include <dlfcn.h>
#include <cstddef>
#include <stdexcept>
#include <string>

namespace schgen::purity_clang {
struct String { const void* data; unsigned flags; };
struct Cursor { unsigned kind; int xdata; const void* data[3]; };
struct Type { unsigned kind; void* data[2]; };
struct Location { const void* data[2]; unsigned value; };
struct Unsaved { const char* name; const char* contents; unsigned long length; };
using Visitor = unsigned (*)(Cursor, Cursor, void*);
using InclusionVisitor = void (*)(void*, Location*, unsigned, void*);

struct Api {
    void* handle = nullptr;
#define PURITY_CLANG_API(result, name, args) result (*name) args = nullptr
    PURITY_CLANG_API(void*, createIndex, (int, int));
    PURITY_CLANG_API(void, disposeIndex, (void*));
    PURITY_CLANG_API(int, parseTranslationUnit2, (void*, const char*, const char* const*, int, Unsaved*, unsigned, unsigned, void**));
    PURITY_CLANG_API(void, disposeTranslationUnit, (void*));
    PURITY_CLANG_API(Cursor, getTranslationUnitCursor, (void*));
    PURITY_CLANG_API(unsigned, visitChildren, (Cursor, Visitor, void*));
    PURITY_CLANG_API(String, getCursorKindSpelling, (unsigned));
    PURITY_CLANG_API(String, getCursorSpelling, (Cursor));
    PURITY_CLANG_API(String, getCursorUSR, (Cursor));
    PURITY_CLANG_API(Cursor, getCursorSemanticParent, (Cursor));
    PURITY_CLANG_API(Cursor, getCursorReferenced, (Cursor));
    PURITY_CLANG_API(Cursor, getCursorDefinition, (Cursor));
    PURITY_CLANG_API(Cursor, getSpecializedCursorTemplate, (Cursor));
    PURITY_CLANG_API(unsigned, isCursorDefinition, (Cursor));
    PURITY_CLANG_API(int, Cursor_isNull, (Cursor));
    PURITY_CLANG_API(unsigned, CXXMethod_isVirtual, (Cursor));
    PURITY_CLANG_API(Type, getCursorType, (Cursor));
    PURITY_CLANG_API(Type, getCursorResultType, (Cursor));
    PURITY_CLANG_API(int, Cursor_getNumArguments, (Cursor));
    PURITY_CLANG_API(Cursor, Cursor_getArgument, (Cursor, unsigned));
    PURITY_CLANG_API(Type, getPointeeType, (Type));
    PURITY_CLANG_API(unsigned, isConstQualifiedType, (Type));
    PURITY_CLANG_API(Type, getCanonicalType, (Type));
    PURITY_CLANG_API(String, getTypeSpelling, (Type));
    PURITY_CLANG_API(Location, getCursorLocation, (Cursor));
    PURITY_CLANG_API(Location, getLocationForOffset, (void*, void*, unsigned));
    PURITY_CLANG_API(void, getExpansionLocation, (Location, void**, unsigned*, unsigned*, unsigned*));
    PURITY_CLANG_API(int, Location_isInSystemHeader, (Location));
    PURITY_CLANG_API(String, getFileName, (void*));
    PURITY_CLANG_API(const char*, getFileContents, (void*, void*, std::size_t*));
    PURITY_CLANG_API(void, getInclusions, (void*, InclusionVisitor, void*));
    PURITY_CLANG_API(unsigned, getNumDiagnostics, (void*));
    PURITY_CLANG_API(void*, getDiagnostic, (void*, unsigned));
    PURITY_CLANG_API(unsigned, getDiagnosticSeverity, (void*));
    PURITY_CLANG_API(String, formatDiagnostic, (void*, unsigned));
    PURITY_CLANG_API(Location, getDiagnosticLocation, (void*));
    PURITY_CLANG_API(void, disposeDiagnostic, (void*));
    PURITY_CLANG_API(String, getClangVersion, ());
    PURITY_CLANG_API(const char*, getCString, (String));
    PURITY_CLANG_API(void, disposeString, (String));
#undef PURITY_CLANG_API
    explicit Api(const std::string& library) {
        if (library.empty()) throw std::runtime_error("an explicit libclang path is required");
        handle = dlopen(library.c_str(), RTLD_NOW | RTLD_LOCAL);
        if (!handle) throw std::runtime_error(std::string("cannot load libclang: ") + dlerror());
        try {
#define LOAD(name) name = reinterpret_cast<decltype(name)>(dlsym(handle, "clang_" #name)); if (!name) throw std::runtime_error("libclang lacks clang_" #name)
            LOAD(createIndex); LOAD(disposeIndex); LOAD(parseTranslationUnit2);
            LOAD(disposeTranslationUnit); LOAD(getTranslationUnitCursor); LOAD(visitChildren);
            LOAD(getCursorKindSpelling); LOAD(getCursorSpelling); LOAD(getCursorUSR);
            LOAD(getCursorSemanticParent); LOAD(getCursorReferenced); LOAD(getCursorDefinition); LOAD(getSpecializedCursorTemplate);
            LOAD(isCursorDefinition); LOAD(Cursor_isNull); LOAD(CXXMethod_isVirtual);
            LOAD(getCursorType); LOAD(getCursorResultType); LOAD(getCanonicalType); LOAD(getTypeSpelling);
            LOAD(Cursor_getNumArguments); LOAD(Cursor_getArgument); LOAD(getPointeeType); LOAD(isConstQualifiedType);
            LOAD(getCursorLocation); LOAD(getLocationForOffset); LOAD(getExpansionLocation); LOAD(Location_isInSystemHeader);
            LOAD(getFileName); LOAD(getFileContents); LOAD(getInclusions); LOAD(getNumDiagnostics); LOAD(getDiagnostic);
            LOAD(getDiagnosticSeverity); LOAD(formatDiagnostic); LOAD(getDiagnosticLocation);
            LOAD(disposeDiagnostic); LOAD(getClangVersion); LOAD(getCString); LOAD(disposeString);
#undef LOAD
        } catch (...) { dlclose(handle); handle = nullptr; throw; }
    }
    ~Api() { if (handle) dlclose(handle); }
    Api(const Api&) = delete;
    Api& operator=(const Api&) = delete;
    std::string text(String s) const {
        const char* p = getCString(s); std::string value = p ? p : "";
        disposeString(s); return value;
    }
};
} // namespace schgen::purity_clang
