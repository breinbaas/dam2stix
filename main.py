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

    # from leveelogic.objects.levee import Levee

    # l = Levee.from_stix(
    #     r"D:\Development\Rijnland\dam2stix\data\output\180-042-00017_962_363_364.stix"
    # )
    # print(l.surface)

    dam_input = DAMInput.from_folder("data/input", SHAPE_FILENAMES)
    dam_input.generate_stix_files("data/output")
