#!/usr/bin/env python3
"""Generate minimal but valid Xcode project.pbxproj files for iOS and macOS NOVA apps."""

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def uid(name: str) -> str:
    return hashlib.md5(name.encode()).hexdigest()[:24].upper()


def collect_swift_files(app_dir: Path) -> list[Path]:
    return sorted(app_dir.rglob("*.swift"))


def generate_pbxproj(
    project_name: str,
    app_dir: Path,
    platform: str,
    bundle_id: str,
    deployment_target: str,
    info_plist: str,
    extra_settings: dict[str, str] | None = None,
) -> str:
    swift_files = collect_swift_files(app_dir)
    file_refs = []
    build_files = []
    sources_phase_ids = []

    for sf in swift_files:
        rel = sf.relative_to(app_dir)
        ref_id = uid(f"ref-{rel}")
        build_id = uid(f"build-{rel}")
        file_refs.append(
            f'\t\t{ref_id} /* {sf.name} */ = {{isa = PBXFileReference; lastKnownFileType = sourcecode.swift; path = "{rel}"; sourceTree = "<group>"; }};'
        )
        build_files.append(
            f"\t\t{build_id} /* {sf.name} in Sources */ = {{isa = PBXBuildFile; fileRef = {ref_id} /* {sf.name} */; }};"
        )
        sources_phase_ids.append(f"\t\t\t\t{build_id} /* {sf.name} in Sources */,")

    plist_ref = uid("info-plist")
    file_refs.append(
        f'\t\t{plist_ref} /* Info.plist */ = {{isa = PBXFileReference; lastKnownFileType = text.plist.xml; path = Info.plist; sourceTree = "<group>"; }};'
    )

    target_id = uid("target")
    project_id = uid("project")
    main_group = uid("main-group")
    products_group = uid("products-group")
    sources_phase = uid("sources-phase")
    frameworks_phase = uid("frameworks-phase")
    resources_phase = uid("resources-phase")
    product_ref = uid("product-ref")
    config_list_proj = uid("config-list-proj")
    config_list_target = uid("config-list-target")
    debug_proj = uid("debug-proj")
    release_proj = uid("release-proj")
    debug_target = uid("debug-target")
    release_target = uid("release-target")
    root_group = uid("root-group")
    nova_group = uid("nova-group")

    sdkroot = "iphoneos" if platform == "ios" else "macosx"
    supported_platforms = "iphoneos iphonesimulator" if platform == "ios" else "macosx"

    extra = extra_settings or {}
    extra_lines = "\n".join(f"\t\t\t\t{k} = {v};" for k, v in extra.items())

    return f"""// !$*UTF8*$!
{{
\tarchiveVersion = 1;
\tclasses = {{
\t}};
\tobjectVersion = 56;
\tobjects = {{

/* Begin PBXBuildFile section */
{chr(10).join(build_files)}
/* End PBXBuildFile section */

/* Begin PBXFileReference section */
{chr(10).join(file_refs)}
\t\t{product_ref} /* {project_name}.app */ = {{isa = PBXFileReference; explicitFileType = wrapper.application; includeInIndex = 0; path = {project_name}.app; sourceTree = BUILT_PRODUCTS_DIR; }};
/* End PBXFileReference section */

/* Begin PBXFrameworksBuildPhase section */
\t\t{frameworks_phase} /* Frameworks */ = {{
\t\t\tisa = PBXFrameworksBuildPhase;
\t\t\tbuildActionMask = 2147483647;
\t\t\tfiles = (
\t\t\t);
\t\t\trunOnlyForDeploymentPostprocessing = 0;
\t\t}};
/* End PBXFrameworksBuildPhase section */

/* Begin PBXGroup section */
\t\t{main_group} = {{
\t\t\tisa = PBXGroup;
\t\t\tchildren = (
\t\t\t\t{nova_group} /* NOVA */,
\t\t\t\t{products_group} /* Products */,
\t\t\t);
\t\t\tsourceTree = "<group>";
\t\t}};
\t\t{nova_group} /* NOVA */ = {{
\t\t\tisa = PBXGroup;
\t\t\tchildren = (
{chr(10).join(f"\t\t\t\t{uid(f'ref-{sf.relative_to(app_dir)}')} /* {sf.name} */," for sf in swift_files)}
\t\t\t\t{plist_ref} /* Info.plist */,
\t\t\t);
\t\t\tpath = NOVA;
\t\t\tsourceTree = "<group>";
\t\t}};
\t\t{products_group} /* Products */ = {{
\t\t\tisa = PBXGroup;
\t\t\tchildren = (
\t\t\t\t{product_ref} /* {project_name}.app */,
\t\t\t);
\t\t\tname = Products;
\t\t\tsourceTree = "<group>";
\t\t}};
/* End PBXGroup section */

/* Begin PBXNativeTarget section */
\t\t{target_id} /* {project_name} */ = {{
\t\t\tisa = PBXNativeTarget;
\t\t\tbuildConfigurationList = {config_list_target} /* Build configuration list for PBXNativeTarget "{project_name}" */;
\t\t\tbuildPhases = (
\t\t\t\t{sources_phase} /* Sources */,
\t\t\t\t{frameworks_phase} /* Frameworks */,
\t\t\t\t{resources_phase} /* Resources */,
\t\t\t);
\t\t\tbuildRules = (
\t\t\t);
\t\t\tdependencies = (
\t\t\t);
\t\t\tname = {project_name};
\t\t\tproductName = {project_name};
\t\t\tproductReference = {product_ref} /* {project_name}.app */;
\t\t\tproductType = "com.apple.product-type.application";
\t\t}};
/* End PBXNativeTarget section */

/* Begin PBXProject section */
\t\t{project_id} /* Project object */ = {{
\t\t\tisa = PBXProject;
\t\t\tattributes = {{
\t\t\t\tBuildIndependentTargetsInParallel = 1;
\t\t\t\tLastSwiftUpdateCheck = 1500;
\t\t\t\tLastUpgradeCheck = 1500;
\t\t\t}};
\t\t\tbuildConfigurationList = {config_list_proj} /* Build configuration list for PBXProject "{project_name}" */;
\t\t\tcompatibilityVersion = "Xcode 14.0";
\t\t\tdevelopmentRegion = en;
\t\t\thasScannedForEncodings = 0;
\t\t\tknownRegions = (
\t\t\t\ten,
\t\t\t\tBase,
\t\t\t);
\t\t\tmainGroup = {main_group};
\t\t\tproductRefGroup = {products_group} /* Products */;
\t\t\tprojectDirPath = "";
\t\t\tprojectRoot = "";
\t\t\ttargets = (
\t\t\t\t{target_id} /* {project_name} */,
\t\t\t);
\t\t}};
/* End PBXProject section */

/* Begin PBXResourcesBuildPhase section */
\t\t{resources_phase} /* Resources */ = {{
\t\t\tisa = PBXResourcesBuildPhase;
\t\t\tbuildActionMask = 2147483647;
\t\t\tfiles = (
\t\t\t);
\t\t\trunOnlyForDeploymentPostprocessing = 0;
\t\t}};
/* End PBXResourcesBuildPhase section */

/* Begin PBXSourcesBuildPhase section */
\t\t{sources_phase} /* Sources */ = {{
\t\t\tisa = PBXSourcesBuildPhase;
\t\t\tbuildActionMask = 2147483647;
\t\t\tfiles = (
{chr(10).join(sources_phase_ids)}
\t\t\t);
\t\t\trunOnlyForDeploymentPostprocessing = 0;
\t\t}};
/* End PBXSourcesBuildPhase section */

/* Begin XCBuildConfiguration section */
\t\t{debug_proj} /* Debug */ = {{
\t\t\tisa = XCBuildConfiguration;
\t\t\tbuildSettings = {{
\t\t\t\tALWAYS_SEARCH_USER_PATHS = NO;
\t\t\t\tCLANG_ENABLE_MODULES = YES;
\t\t\t\tCOPY_PHASE_STRIP = NO;
\t\t\t\tDEBUG_INFORMATION_FORMAT = dwarf;
\t\t\t\tENABLE_TESTABILITY = YES;
\t\t\t\tGCC_DYNAMIC_NO_PIC = NO;
\t\t\t\tGCC_OPTIMIZATION_LEVEL = 0;
\t\t\t\tGCC_PREPROCESSOR_DEFINITIONS = (
\t\t\t\t\t"DEBUG=1",
\t\t\t\t\t"$(inherited)",
\t\t\t\t);
\t\t\t\tMTL_ENABLE_DEBUG_INFO = INCLUDE_SOURCE;
\t\t\t\tONLY_ACTIVE_ARCH = YES;
\t\t\t\tSDKROOT = {sdkroot};
\t\t\t\tSWIFT_ACTIVE_COMPILATION_CONDITIONS = DEBUG;
\t\t\t\tSWIFT_OPTIMIZATION_LEVEL = "-Onone";
\t\t\t}};
\t\t\tname = Debug;
\t\t}};
\t\t{release_proj} /* Release */ = {{
\t\t\tisa = XCBuildConfiguration;
\t\t\tbuildSettings = {{
\t\t\t\tALWAYS_SEARCH_USER_PATHS = NO;
\t\t\t\tCLANG_ENABLE_MODULES = YES;
\t\t\t\tCOPY_PHASE_STRIP = NO;
\t\t\t\tDEBUG_INFORMATION_FORMAT = "dwarf-with-dsym";
\t\t\t\tENABLE_NS_ASSERTIONS = NO;
\t\t\t\tMTL_ENABLE_DEBUG_INFO = NO;
\t\t\t\tSDKROOT = {sdkroot};
\t\t\t\tSWIFT_COMPILATION_MODE = wholemodule;
\t\t\t\tSWIFT_OPTIMIZATION_LEVEL = "-O";
\t\t\t}};
\t\t\tname = Release;
\t\t}};
\t\t{debug_target} /* Debug */ = {{
\t\t\tisa = XCBuildConfiguration;
\t\t\tbuildSettings = {{
\t\t\t\tCODE_SIGN_STYLE = Automatic;
\t\t\t\tCURRENT_PROJECT_VERSION = 1;
\t\t\t\tGENERATE_INFOPLIST_FILE = NO;
\t\t\t\tINFOPLIST_FILE = {info_plist};
\t\t\t\tMARKETING_VERSION = 0.1.0;
\t\t\t\tPRODUCT_BUNDLE_IDENTIFIER = {bundle_id};
\t\t\t\tPRODUCT_NAME = "$(TARGET_NAME)";
\t\t\t\tSWIFT_EMIT_LOC_STRINGS = YES;
\t\t\t\tSWIFT_VERSION = 5.0;
{extra_lines}
\t\t\t\tIPHONEOS_DEPLOYMENT_TARGET = {deployment_target};
\t\t\t\tSUPPORTED_PLATFORMS = "{supported_platforms}";
\t\t\t\tTARGETED_DEVICE_FAMILY = "1,2";
\t\t\t}};
\t\t\tname = Debug;
\t\t}};
\t\t{release_target} /* Release */ = {{
\t\t\tisa = XCBuildConfiguration;
\t\t\tbuildSettings = {{
\t\t\t\tCODE_SIGN_STYLE = Automatic;
\t\t\t\tCURRENT_PROJECT_VERSION = 1;
\t\t\t\tGENERATE_INFOPLIST_FILE = NO;
\t\t\t\tINFOPLIST_FILE = {info_plist};
\t\t\t\tMARKETING_VERSION = 0.1.0;
\t\t\t\tPRODUCT_BUNDLE_IDENTIFIER = {bundle_id};
\t\t\t\tPRODUCT_NAME = "$(TARGET_NAME)";
\t\t\t\tSWIFT_EMIT_LOC_STRINGS = YES;
\t\t\t\tSWIFT_VERSION = 5.0;
{extra_lines}
\t\t\t\tIPHONEOS_DEPLOYMENT_TARGET = {deployment_target};
\t\t\t\tSUPPORTED_PLATFORMS = "{supported_platforms}";
\t\t\t\tTARGETED_DEVICE_FAMILY = "1,2";
\t\t\t}};
\t\t\tname = Release;
\t\t}};
/* End XCBuildConfiguration section */

/* Begin XCConfigurationList section */
\t\t{config_list_proj} /* Build configuration list for PBXProject "{project_name}" */ = {{
\t\t\tisa = XCConfigurationList;
\t\t\tbuildConfigurations = (
\t\t\t\t{debug_proj} /* Debug */,
\t\t\t\t{release_proj} /* Release */,
\t\t\t);
\t\t\tdefaultConfigurationIsVisible = 0;
\t\t\tdefaultConfigurationName = Release;
\t\t}};
\t\t{config_list_target} /* Build configuration list for PBXNativeTarget "{project_name}" */ = {{
\t\t\tisa = XCConfigurationList;
\t\t\tbuildConfigurations = (
\t\t\t\t{debug_target} /* Debug */,
\t\t\t\t{release_target} /* Release */,
\t\t\t);
\t\t\tdefaultConfigurationIsVisible = 0;
\t\t\tdefaultConfigurationName = Release;
\t\t}};
/* End XCConfigurationList section */
\t}};
\trootObject = {project_id} /* Project object */;
}}
"""


def generate_macos_pbxproj(project_name, app_dir, bundle_id, deployment_target, info_plist):
    """macOS variant without iOS-specific settings."""
    content = generate_pbxproj(
        project_name,
        app_dir,
        "macos",
        bundle_id,
        deployment_target,
        info_plist,
        extra_settings={
            "MACOSX_DEPLOYMENT_TARGET": deployment_target,
            "LSUIElement": "YES",
            "OTHER_LDFLAGS": '"-framework Carbon"',
        },
    )
    # Remove iOS-specific lines for macOS
    content = content.replace("IPHONEOS_DEPLOYMENT_TARGET", "MACOSX_DEPLOYMENT_TARGET")
    content = content.replace(
        'SUPPORTED_PLATFORMS = "iphoneos iphonesimulator";', "SUPPORTED_PLATFORMS = macosx;"
    )
    content = content.replace('TARGETED_DEVICE_FAMILY = "1,2";', "")
    content = content.replace("SDKROOT = iphoneos;", "SDKROOT = macosx;")
    return content


def inject_unit_test_target(
    pbx_content: str,
    *,
    app_target_name: str,
    test_target_name: str,
    test_bundle_id: str,
    test_files: list[Path],
    platform: str,
    host_app_name: str,
) -> str:
    if not test_files:
        return pbx_content
    app_target_id = uid("target")
    test_target_id = uid(f"test-target-{test_target_name}")
    test_product_ref = uid(f"test-product-{test_target_name}")
    test_sources_phase = uid(f"test-sources-{test_target_name}")
    test_frameworks_phase = uid(f"test-frameworks-{test_target_name}")
    test_config_list = uid(f"test-config-list-{test_target_name}")
    test_debug = uid(f"test-debug-{test_target_name}")
    test_release = uid(f"test-release-{test_target_name}")
    test_group = uid(f"test-group-{test_target_name}")
    proxy_id = uid(f"test-proxy-{test_target_name}")
    dep_id = uid(f"test-dep-{test_target_name}")

    file_refs = []
    build_files = []
    source_lines = []
    for sf in test_files:
        rel = sf.name
        ref_id = uid(f"test-ref-{test_target_name}-{rel}")
        build_id = uid(f"test-build-{test_target_name}-{rel}")
        file_refs.append(
            f'\t\t{ref_id} /* {sf.name} */ = {{isa = PBXFileReference; lastKnownFileType = sourcecode.swift; path = "{rel}"; sourceTree = "<group>"; }};'
        )
        build_files.append(
            f"\t\t{build_id} /* {sf.name} in Sources */ = {{isa = PBXBuildFile; fileRef = {ref_id} /* {sf.name} */; }};"
        )
        source_lines.append(f"\t\t\t\t{build_id} /* {sf.name} in Sources */,")

    sdkroot = "iphoneos" if platform == "ios" else "macosx"
    test_platform = "iphonesimulator" if platform == "ios" else "macosx"
    host_settings = (
        f'BUNDLE_LOADER = "$(TEST_HOST)";\n\t\t\t\tTEST_HOST = "$(BUILT_PRODUCTS_DIR)/{host_app_name}.app/$(BUNDLE_EXECUTABLE_FOLDER_PATH)/{host_app_name}";'
        if platform == "ios"
        else f'BUNDLE_LOADER = "$(TEST_HOST)";\n\t\t\t\tTEST_HOST = "$(BUILT_PRODUCTS_DIR)/{host_app_name}.app/Contents/MacOS/{host_app_name}";'
    )

    pbx_content = pbx_content.replace(
        "/* Begin PBXBuildFile section */",
        "/* Begin PBXBuildFile section */\n" + "\n".join(build_files),
        1,
    )
    pbx_content = pbx_content.replace(
        "/* Begin PBXFileReference section */",
        "/* Begin PBXFileReference section */\n"
        + "\n".join(file_refs)
        + f"\n\t\t{test_product_ref} /* {test_target_name}.xctest */ = {{isa = PBXFileReference; explicitFileType = wrapper.cfbundle; includeInIndex = 0; path = {test_target_name}.xctest; sourceTree = BUILT_PRODUCTS_DIR; }};",
        1,
    )
    pbx_content = pbx_content.replace(
        "/* Begin PBXFileReference section */",
        "/* Begin PBXFileReference section */\n"
        + "\n".join(file_refs)
        + f"\n\t\t{test_product_ref} /* {test_target_name}.xctest */ = {{isa = PBXFileReference; explicitFileType = wrapper.cfbundle; includeInIndex = 0; path = {test_target_name}.xctest; sourceTree = BUILT_PRODUCTS_DIR; }};",
        1,
    )

    native_target_block = f"""
\t\t{test_target_id} /* {test_target_name} */ = {{
\t\t\tisa = PBXNativeTarget;
\t\t\tbuildConfigurationList = {test_config_list} /* Build configuration list for PBXNativeTarget "{test_target_name}" */;
\t\t\tbuildPhases = (
\t\t\t\t{test_sources_phase} /* Sources */,
\t\t\t\t{test_frameworks_phase} /* Frameworks */,
\t\t\t);
\t\t\tbuildRules = (
\t\t\t);
\t\t\tdependencies = (
\t\t\t\t{dep_id} /* PBXTargetDependency */,
\t\t\t);
\t\t\tname = {test_target_name};
\t\t\tproductName = {test_target_name};
\t\t\tproductReference = {test_product_ref} /* {test_target_name}.xctest */;
\t\t\tproductType = "com.apple.product-type.bundle.unit-test";
\t\t}};
"""

    proxy_block = f"""
/* Begin PBXContainerItemProxy section */
\t\t{proxy_id} /* PBXContainerItemProxy */ = {{
\t\t\tisa = PBXContainerItemProxy;
\t\t\tcontainerPortal = {uid("project")} /* Project object */;
\t\t\tproxyType = 1;
\t\t\tremoteGlobalIDString = {app_target_id};
\t\t\tremoteInfo = {app_target_name};
\t\t}};
/* End PBXContainerItemProxy section */

/* Begin PBXTargetDependency section */
\t\t{dep_id} /* PBXTargetDependency */ = {{
\t\t\tisa = PBXTargetDependency;
\t\t\ttarget = {app_target_id} /* {app_target_name} */;
\t\t\ttargetProxy = {proxy_id} /* PBXContainerItemProxy */;
\t\t}};
/* End PBXTargetDependency section */
"""

    test_group_block = f"""
\t\t{test_group} /* {test_target_name} */ = {{
\t\t\tisa = PBXGroup;
\t\t\tchildren = (
{chr(10).join(f"\t\t\t\t{uid(f'test-ref-{test_target_name}-{sf.name}')} /* {sf.name} */," for sf in test_files)}
\t\t\t);
\t\t\tpath = {test_target_name};
\t\t\tsourceTree = "<group>";
\t\t}};
"""

    test_sources_block = f"""
\t\t{test_sources_phase} /* Sources */ = {{
\t\t\tisa = PBXSourcesBuildPhase;
\t\t\tbuildActionMask = 2147483647;
\t\t\tfiles = (
{chr(10).join(source_lines)}
\t\t\t);
\t\t\trunOnlyForDeploymentPostprocessing = 0;
\t\t}};
"""

    test_frameworks_block = f"""
\t\t{test_frameworks_phase} /* Frameworks */ = {{
\t\t\tisa = PBXFrameworksBuildPhase;
\t\t\tbuildActionMask = 2147483647;
\t\t\tfiles = (
\t\t\t);
\t\t\trunOnlyForDeploymentPostprocessing = 0;
\t\t}};
"""

    test_config_block = f"""
\t\t{test_debug} /* Debug */ = {{
\t\t\tisa = XCBuildConfiguration;
\t\t\tbuildSettings = {{
\t\t\t\tCODE_SIGN_STYLE = Automatic;
\t\t\t\tGENERATE_INFOPLIST_FILE = YES;
\t\t\t\t{host_settings}
\t\t\t\tIPHONEOS_DEPLOYMENT_TARGET = 17.0;
\t\t\t\tMACOSX_DEPLOYMENT_TARGET = 14.0;
\t\t\t\tPRODUCT_BUNDLE_IDENTIFIER = {test_bundle_id};
\t\t\t\tPRODUCT_NAME = "$(TARGET_NAME)";
\t\t\t\tSDKROOT = {sdkroot};
\t\t\t\tSUPPORTED_PLATFORMS = "{test_platform}";
\t\t\t\tSWIFT_VERSION = 5.0;
\t\t\t\tLD_RUNPATH_SEARCH_PATHS = (
\t\t\t\t\t"$(inherited)",
\t\t\t\t\t"@executable_path/Frameworks",
\t\t\t\t\t"@loader_path/Frameworks",
\t\t\t\t);
\t\t\t}};
\t\t\tname = Debug;
\t\t}};
\t\t{test_release} /* Release */ = {{
\t\t\tisa = XCBuildConfiguration;
\t\t\tbuildSettings = {{
\t\t\t\tCODE_SIGN_STYLE = Automatic;
\t\t\t\tGENERATE_INFOPLIST_FILE = YES;
\t\t\t\t{host_settings}
\t\t\t\tIPHONEOS_DEPLOYMENT_TARGET = 17.0;
\t\t\t\tMACOSX_DEPLOYMENT_TARGET = 14.0;
\t\t\t\tPRODUCT_BUNDLE_IDENTIFIER = {test_bundle_id};
\t\t\t\tPRODUCT_NAME = "$(TARGET_NAME)";
\t\t\t\tSDKROOT = {sdkroot};
\t\t\t\tSUPPORTED_PLATFORMS = "{test_platform}";
\t\t\t\tSWIFT_VERSION = 5.0;
\t\t\t}};
\t\t\tname = Release;
\t\t}};
\t\t{test_config_list} /* Build configuration list for PBXNativeTarget "{test_target_name}" */ = {{
\t\t\tisa = XCConfigurationList;
\t\t\tbuildConfigurations = (
\t\t\t\t{test_debug} /* Debug */,
\t\t\t\t{test_release} /* Release */,
\t\t\t);
\t\t\tdefaultConfigurationIsVisible = 0;
\t\t\tdefaultConfigurationName = Release;
\t\t}};
"""

    pbx_content = pbx_content.replace(
        "/* End PBXNativeTarget section */",
        native_target_block + "\n/* End PBXNativeTarget section */",
        1,
    )
    pbx_content = pbx_content.replace(
        "/* End PBXNativeTarget section */",
        "/* End PBXNativeTarget section */\n" + proxy_block,
        1,
    )
    pbx_content = pbx_content.replace(
        "/* End PBXGroup section */",
        test_group_block + "\n/* End PBXGroup section */",
        1,
    )
    pbx_content = pbx_content.replace(
        "/* End PBXSourcesBuildPhase section */",
        test_sources_block + "\n/* End PBXSourcesBuildPhase section */",
        1,
    )
    pbx_content = pbx_content.replace(
        "/* End PBXFrameworksBuildPhase section */",
        test_frameworks_block + "\n/* End PBXFrameworksBuildPhase section */",
        1,
    )
    pbx_content = pbx_content.replace(
        "/* End XCBuildConfiguration section */",
        test_config_block + "\n/* End XCBuildConfiguration section */",
        1,
    )
    injection = ""
    pbx_content = pbx_content.replace(
        f"\t\t\ttargets = (\n\t\t\t\t{app_target_id} /* {app_target_name} */,\n\t\t\t);",
        f"\t\t\ttargets = (\n\t\t\t\t{app_target_id} /* {app_target_name} */,\n\t\t\t\t{test_target_id} /* {test_target_name} */,\n\t\t\t);",
        1,
    )
    pbx_content = pbx_content.replace(
        f"\t\t\tchildren = (\n\t\t\t\t{uid('nova-group')} /* NOVA */,",
        f"\t\t\tchildren = (\n\t\t\t\t{uid('nova-group')} /* NOVA */,\n\t\t\t\t{test_group} /* {test_target_name} */,",
        1,
    )
    pbx_content = pbx_content.replace(
        f"\t\t\tchildren = (\n\t\t\t\t{uid('product-ref')} /* {app_target_name}.app */,",
        f"\t\t\tchildren = (\n\t\t\t\t{uid('product-ref')} /* {app_target_name}.app */,\n\t\t\t\t{test_product_ref} /* {test_target_name}.xctest */,",
        1,
    )
    return pbx_content


def write_scheme_with_tests(
    base: Path, proj_name: str, scheme_name: str, test_target_name: str
) -> None:
    scheme_dir = base / f"{proj_name}.xcodeproj" / "xcshareddata" / "xcschemes"
    scheme_dir.mkdir(parents=True, exist_ok=True)
    test_target_id = uid(f"test-target-{test_target_name}")
    (scheme_dir / f"{scheme_name}.xcscheme").write_text(
        f"""<?xml version="1.0" encoding="UTF-8"?>
<Scheme LastUpgradeVersion="1500" version="1.7">
   <BuildAction parallelizeBuildables="YES" buildImplicitDependencies="YES">
      <BuildActionEntries>
         <BuildActionEntry buildForTesting="YES" buildForRunning="YES" buildForProfiling="YES" buildForArchiving="YES" buildForAnalyzing="YES">
            <BuildableReference BuildableIdentifier="primary" BlueprintIdentifier="{uid("target")}" BuildableName="{scheme_name}.app" BlueprintName="{scheme_name}" ReferencedContainer="container:{proj_name}.xcodeproj"/>
         </BuildActionEntry>
         <BuildActionEntry buildForTesting="YES" buildForRunning="NO" buildForProfiling="NO" buildForArchiving="NO" buildForAnalyzing="NO">
            <BuildableReference BuildableIdentifier="primary" BlueprintIdentifier="{test_target_id}" BuildableName="{test_target_name}.xctest" BlueprintName="{test_target_name}" ReferencedContainer="container:{proj_name}.xcodeproj"/>
         </BuildActionEntry>
      </BuildActionEntries>
   </BuildAction>
   <TestAction buildConfiguration="Debug" selectedDebuggerIdentifier="Xcode.DebuggerFoundation.Debugger.LLDB" selectedLauncherIdentifier="Xcode.DebuggerFoundation.Launcher.LLDB" shouldUseLaunchSchemeArgsEnv="YES">
      <Testables>
         <TestableReference skipped="NO">
            <BuildableReference BuildableIdentifier="primary" BlueprintIdentifier="{test_target_id}" BuildableName="{test_target_name}.xctest" BlueprintName="{test_target_name}" ReferencedContainer="container:{proj_name}.xcodeproj"/>
         </TestableReference>
      </Testables>
   </TestAction>
   <LaunchAction buildConfiguration="Debug" selectedDebuggerIdentifier="Xcode.DebuggerFoundation.Debugger.LLDB" selectedLauncherIdentifier="Xcode.DebuggerFoundation.Launcher.LLDB" launchStyle="0" useCustomWorkingDirectory="NO" ignoresPersistentStateOnLaunch="NO" debugDocumentVersioning="YES" debugServiceExtension="internal" allowLocationSimulation="YES">
      <BuildableProductRunnable runnableDebuggingMode="0">
         <BuildableReference BuildableIdentifier="primary" BlueprintIdentifier="{uid("target")}" BuildableName="{scheme_name}.app" BlueprintName="{scheme_name}" ReferencedContainer="container:{proj_name}.xcodeproj"/>
      </BuildableProductRunnable>
   </LaunchAction>
</Scheme>
"""
    )


def main() -> None:
    ios_dir = ROOT / "apps" / "ios"
    macos_dir = ROOT / "apps" / "macos"

    ios_pbx = ios_dir / "NOVA.xcodeproj" / "project.pbxproj"
    ios_pbx.parent.mkdir(parents=True, exist_ok=True)
    ios_content = generate_pbxproj(
        "NOVA", ios_dir / "NOVA", "ios", "com.nova.ios", "17.0", "NOVA/Info.plist"
    )
    ios_tests = collect_swift_files(ios_dir / "NOVATests")
    ios_content = inject_unit_test_target(
        ios_content,
        app_target_name="NOVA",
        test_target_name="NOVATests",
        test_bundle_id="com.nova.ios.tests",
        test_files=ios_tests,
        platform="ios",
        host_app_name="NOVA",
    )
    ios_pbx.write_text(ios_content)

    macos_pbx = macos_dir / "NOVAGenie.xcodeproj" / "project.pbxproj"
    macos_pbx.parent.mkdir(parents=True, exist_ok=True)
    macos_content = generate_macos_pbxproj(
        "NOVAGenie", macos_dir / "NOVA", "com.nova.macos.genie", "14.0", "NOVA/Info.plist"
    )
    macos_tests = collect_swift_files(macos_dir / "NOVAGenieTests")
    macos_content = inject_unit_test_target(
        macos_content,
        app_target_name="NOVAGenie",
        test_target_name="NOVAGenieTests",
        test_bundle_id="com.nova.macos.tests",
        test_files=macos_tests,
        platform="macos",
        host_app_name="NOVAGenie",
    )
    macos_pbx.write_text(macos_content)

    write_scheme_with_tests(ios_dir, "NOVA", "NOVA", "NOVATests")
    write_scheme_with_tests(macos_dir, "NOVAGenie", "NOVAGenie", "NOVAGenieTests")

    print(f"Generated {ios_pbx}")
    print(f"Generated {macos_pbx}")
    print(f"iOS pbxproj sha256: {hashlib.sha256(ios_pbx.read_bytes()).hexdigest()}")
    print(f"macOS pbxproj sha256: {hashlib.sha256(macos_pbx.read_bytes()).hexdigest()}")


if __name__ == "__main__":
    main()
