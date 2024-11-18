from objects import DAMInput
import logging

logging.basicConfig(
    filename="dam2stix.log",
    filemode="w",
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
    level=logging.INFO,
)

# hier kun je de namen van de te gebruiken shape files definieren, zie README
SHAPE_FILENAMES = {
    "polderpeilen": "locations_peilen",
    "stijghoogte": "stijghoogteAtLocations",
    "toetspeilen": "toetspeil_V1",
}

if __name__ == "__main__":
    dam_input = DAMInput.from_folder("data/input", SHAPE_FILENAMES)
    dam_input.generate_stix_files("data/output")
