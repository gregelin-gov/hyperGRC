# Routines for loading OpenControl data.

import os.path
import rtyaml

def short_hash(s, len=6):
    import hashlib
    hasher = hashlib.sha256()
    hasher.update(s.encode("utf8"))
    return hasher.hexdigest()[:len]

def load_project_from_path(project_dir):
    from urllib.parse import quote_plus

    # Read the opencontrol file for the system name, description, etc.
    # If there is no name, fall back to the project directory name.
    fn = os.path.join(project_dir, "opencontrol.yaml")
    with open(fn, encoding="utf8") as f:
        opencontrol = rtyaml.load(f)
        if opencontrol.get("schema_version") != "1.0.0":
            raise ValueError("Don't know how to read OpenControl system file {} which has schema_version {}.".format(fn, opencontrol.get("schema_version")))

        # read OpenControl system metadata
        name = opencontrol.get("name") or os.path.splitext(os.path.basename(os.path.normpath(project_dir)))[0]
        description = opencontrol.get("metadata", {}).get("description")

        # read hyperGRC extensions
        organization_name = opencontrol.get("metadata", {}).get("organization", {}).get("name", "No Organization")
        organization_abbrev = opencontrol.get("metadata", {}).get("organization", {}).get("abbreviation", organization_name)
        organization_id = organization_abbrev[0:12] + "-" + short_hash(organization_name)

        # make an identifier
        project_id = name[0:12] + "-" + short_hash(fn)

    return {
        "id": project_id,
        "organization": {
            "id": organization_id,
            "name": organization_name,
            "abbreviation": organization_abbrev,
        },
        "title": name,
        "path": project_dir,
        "description": description,
        "url": "/organizations/{}/projects/{}".format(
            quote_plus(organization_id),
            quote_plus(project_id)
        ),
    }

def load_project_components(project):
    # Read the project's opencontrol.yaml file and
    # then read each component's component.yaml file
    # and return a generator over components.
    from urllib.parse import quote_plus
    fn1 = os.path.join(project["path"], "opencontrol.yaml")
    with open(fn1, encoding="utf8") as f1:
        opencontrol = rtyaml.load(f1)
        if opencontrol.get("schema_version") != "1.0.0":
            raise ValueError("Don't know how to read OpenControl system file {} which has schema_version {}.".format(fn1, opencontrol.get("schema_version")))
        
        for component_path in opencontrol.get("components", []):
            fn2 = os.path.join(project["path"], component_path, "component.yaml")
            with open(fn2, encoding="utf8") as f2:
                component = rtyaml.load(f2)
                if component.get("schema_version") != "3.0.0":
                    raise ValueError("Don't know how to read OpenControl component file {} which has schema_version {}.".format(fn2, component.get("schema_version")))

                # Get the component name. If there is no name, fall back to the directory name.
                name = component.get("name") or os.path.splitext(os.path.basename(os.path.normpath(component_path)))[0]

                # Make a URL-safe, stable component identifier.
                component_id = name[0:12] + "-" + short_hash(component_path)

                yield {
                    "project": project,
                    "id": component_id,
                    "path": os.path.join(project["path"], component_path),
                    "name": name,
                    "url": project["url"] + "/components/" + quote_plus(component_id),
                }

def load_project_component(project, component_id):
    for component in load_project_components(project):
        if component["id"] == component_id:
            return component
    raise ValueError("Component {} does not exist in project {}.".format(component_id, project["id"]))

def intify(s):
    try:
        return int(s)
    except ValueError:
        return s
def make_control_number_sort_key(s):
    import re
    return tuple(intify(part) for part in re.split(r"(\d+)", s or ""))

def load_project_standards(project):
    # Return a mapping from standard_keys to parsed standard data.

    # The OpenControl file for the system (project) has a list of standards...
    fn1 = os.path.join(project["path"], "opencontrol.yaml")
    with open(fn1, encoding="utf8") as f1:
        system_opencontrol = rtyaml.load(f1)
        if system_opencontrol.get("schema_version") != "1.0.0":
            raise ValueError("Don't know how to read OpenControl system file {} which has schema_version {}.".format(fn1, system_opencontrol.get("schema_version")))
    for standards_dir in system_opencontrol["standards"]:

        # Each standard is a directory containing an opencontrol file...
        fn2 = os.path.join(project["path"], standards_dir, "opencontrol.yaml")
        with open(fn2, encoding="utf8") as f2:
            standards_opencontrol = rtyaml.load(f2)
            if standards_opencontrol.get("schema_version") != "1.0.0":
               raise ValueError("Don't know how to read OpenControl standards file {} which has schema_version {}.".format(fn2, standards_opencontrol.get("schema_version")))

            # And this file contains a list of standards YAML files...
            for standard_fn in standards_opencontrol.get("standards", []):
                fn3 = os.path.join(project["path"], standards_dir, standard_fn)
                standard_key = os.path.splitext(os.path.basename(os.path.normpath(fn3)))[0]

                # Which we can then read.
                with open(fn3, encoding="utf8") as f3:
                    standard_opencontrol = rtyaml.load(f3)

                    # Create a dict holding information about the standard and the controls
                    # within the standard.
                    standard = {
                        "id": standard_key,
                        "name": standard_opencontrol["name"],
                        "controls": {
                            control_number: { # must match control structure in load_project_component_controls, except the URL
                                "id": control_number, # matches how the control is put in the URL
                                "sort_key": (standard_key, make_control_number_sort_key(control_number)),
                                "number": control_number,
                                "name": control_data["name"],
                                "family": control_data["family"],
                                "description": control_data["description"],
                            }
                            for control_number, control_data in standard_opencontrol.items()
                            if isinstance(control_data, dict) # not the "name: " key
                               and control_data.get('type') is None # skip the family names that we put in the file but aren't in the OpenControl standard
                        },
                        "families": {
                            family_id: { # must match control structure in load_project_component_controls, except the URL
                                "id": family_id, # matches how the control is put in the URL
                                "sort_key": family_id,
                                "number": family_id,
                                "name": family_data["name"],
                            }
                            for family_id, family_data in standard_opencontrol.items()
                            if isinstance(family_data, dict) # not the "name: " key
                               and family_data.get('type') == 'family' # not in OpenControl --- we've added family names to the standard
                        },
                    }
                yield (standard_key, standard)

def load_project_component_controls(component, standards):
    # Return a generator over all of the controls implemented by the component.
    
    from urllib.parse import quote_plus

    fn = os.path.join(component["path"], "component.yaml")
    with open(fn, encoding="utf8") as f:
        component_opencontrol = rtyaml.load(f)
        if component_opencontrol.get("schema_version") != "3.0.0":
            raise ValueError("Don't know how to read OpenControl component file {} which has schema_version {}.".format(fn, component_opencontrol.get("schema_version")))

        for control in component_opencontrol.get("satisfies", []):
            # For each control, yield a dict holding the control
            # number, name, etc. Because of UI limitations, yield
            # a separate control record for each control *part*.

            # Create basic metadata for the control only based on what's in the
            # component.
            control_metadata = {
                "component": component,
                "standard": {
                    "id": control["standard_key"], # matches how the control is put in the URL
                    "name": control["standard_key"],
                },
                "family": {
                    "abbrev": control["control_key"].split("-")[0],
                    "name": control["control_key"].split("-")[0],
                    "sort_key": control["control_key"].split("-")[0],
                },
                "control": { # must match control structure in load_project_standards
                    "id": control["control_key"], # matches how the control is put in the URL
                    "sort_key": (control["standard_key"], make_control_number_sort_key(control["control_key"])),
                    "number": control["control_key"],
                    "name": control["name"], # not in OpenControl spec
                    "url": "{}/controls/{}/{}".format(
                        component["project"]["url"],
                        quote_plus(control["standard_key"]),
                        quote_plus(control["control_key"]),
                    )
                },
                "source_file": fn,
            }

            # Look up the standard and add standard metadata.
            if control["standard_key"] in standards:
                standard = standards[control["standard_key"]]
                control_metadata["standard"]["name"] = standard["name"]

                # If the control is in the standard, add its info also.
                if control["control_key"] in standard["controls"]:
                    control_metadata["control"].update(standard["controls"][control["control_key"]])

                    # If the control's family is in the standard, add its info also.
                    if control_metadata["control"].get("family") in standard["families"]:
                        control_metadata["family"].update(standard["families"][control_metadata["control"]["family"]])

            # For each narrative part, make a copy of the control metadata
            # so far, add the control part, and return the combined metadata.
            import copy
            for narrative_part in control.get("narrative", []):
                controlimpl = dict(control_metadata)
                controlimpl.update({
                    "control_part": narrative_part.get("key"),
                    "sort_key": (controlimpl["control"]["sort_key"], make_control_number_sort_key(narrative_part.get("key"))),
                    "narrative": narrative_part["text"],
                })
                yield controlimpl

def update_component_control(controlimpl):
    # The control is defined in the component.yaml file given in controlimpl["source_file"].
    # Open that file for editing, find the control record, update it, and return.

    with open(controlimpl["source_file"], "r+", encoding="utf8") as f:
        # Parse the content.
        data = rtyaml.load(f)

        # Look for a matching control entry.
        for control in data["satisfies"]:
            if control["standard_key"] == controlimpl["standard"]["id"] \
              and control["control_key"] == controlimpl["control"]["id"]:

                for narrative_part in control.get("narrative", []):
                    if narrative_part.get("key") == controlimpl.get("control_part"):
                        # Found the right entry. Update the fields.
                        narrative_part["text"] = controlimpl["narrative"]


        # Write back out to the data files.
        f.seek(0);
        f.truncate()
        rtyaml.dump(data, f)
