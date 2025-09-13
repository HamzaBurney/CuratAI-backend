def validate_project_name(project_name: str) -> bool:
    """
    Validate the project name to ensure it is not empty and contains only
    alphanumeric characters, dashes (-), and underscores (_).

    Args:
        project_name (str): The project name to validate.

    Returns:
        bool: True if valid, False otherwise.
    """
    if not project_name:
        return False

    allowed_characters = project_name.replace("-", "").replace("_", "").isalnum()
    return allowed_characters