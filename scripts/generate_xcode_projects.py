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
        extra_settings={"MACOSX_DEPLOYMENT_TARGET": deployment_target, "LSUIElement": "YES"},
    )
    # Remove iOS-specific lines for macOS
    content = content.replace("IPHONEOS_DEPLOYMENT_TARGET", "MACOSX_DEPLOYMENT_TARGET")
    content = content.replace(
        'SUPPORTED_PLATFORMS = "iphoneos iphonesimulator";', "SUPPORTED_PLATFORMS = macosx;"
    )
    content = content.replace('TARGETED_DEVICE_FAMILY = "1,2";', "")
    content = content.replace("SDKROOT = iphoneos;", "SDKROOT = macosx;")
    return content


def main() -> None:
    ios_dir = ROOT / "apps" / "ios"
    macos_dir = ROOT / "apps" / "macos"

    ios_pbx = ios_dir / "NOVA.xcodeproj" / "project.pbxproj"
    ios_pbx.parent.mkdir(parents=True, exist_ok=True)
    ios_pbx.write_text(
        generate_pbxproj("NOVA", ios_dir / "NOVA", "ios", "com.nova.ios", "17.0", "NOVA/Info.plist")
    )

    macos_pbx = macos_dir / "NOVAGenie.xcodeproj" / "project.pbxproj"
    macos_pbx.parent.mkdir(parents=True, exist_ok=True)
    macos_pbx.write_text(
        generate_macos_pbxproj(
            "NOVAGenie", macos_dir / "NOVA", "com.nova.macos.genie", "14.0", "NOVA/Info.plist"
        )
    )

    # Create shared scheme
    for proj_name, scheme_name in [("NOVA", "NOVA"), ("NOVAGenie", "NOVAGenie")]:
        base = ios_dir if proj_name == "NOVA" else macos_dir
        scheme_dir = base / f"{proj_name}.xcodeproj" / "xcshareddata" / "xcschemes"
        scheme_dir.mkdir(parents=True, exist_ok=True)
        (
            scheme_dir / f"{scheme_name}.xcscheme"
        ).write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<Scheme LastUpgradeVersion="1500" version="1.7">
   <BuildAction parallelizeBuildables="YES" buildImplicitDependencies="YES">
      <BuildActionEntries>
         <BuildActionEntry buildForTesting="YES" buildForRunning="YES" buildForProfiling="YES" buildForArchiving="YES" buildForAnalyzing="YES">
            <BuildableReference BuildableIdentifier="primary" BlueprintIdentifier="TARGET" BuildableName="{scheme_name}.app" BlueprintName="{scheme_name}" ReferencedContainer="container:{proj_name}.xcodeproj"/>
         </BuildActionEntry>
      </BuildActionEntries>
   </BuildAction>
   <LaunchAction buildConfiguration="Debug" selectedDebuggerIdentifier="Xcode.DebuggerFoundation.Debugger.LLDB" selectedLauncherIdentifier="Xcode.DebuggerFoundation.Launcher.LLDB" launchStyle="0" useCustomWorkingDirectory="NO" ignoresPersistentStateOnLaunch="NO" debugDocumentVersioning="YES" debugServiceExtension="internal" allowLocationSimulation="YES">
      <BuildableProductRunnable runnableDebuggingMode="0">
         <BuildableReference BuildableIdentifier="primary" BlueprintIdentifier="TARGET" BuildableName="{scheme_name}.app" BlueprintName="{scheme_name}" ReferencedContainer="container:{proj_name}.xcodeproj"/>
      </BuildableProductRunnable>
   </LaunchAction>
</Scheme>
""")

    print(f"Generated {ios_pbx}")
    print(f"Generated {macos_pbx}")


if __name__ == "__main__":
    main()
