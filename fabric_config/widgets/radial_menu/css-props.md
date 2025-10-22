# How it works 

- init with size, children(of type Label or Image only...)
- css props for each slice given by index number or custom class name for child
    - children = [Image, Image, Label, Label]
    - children_classes = [_, _, _, "custom-class"]

    OR
    - children = List of Optional Tuple((Label or Image), class_name)
        - example: children = [(Image, "dog"), Label, (Label, "app-menu-slice")]
