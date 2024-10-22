from objects import DAMInput
import logging

logging.basicConfig(
    filename="dam2stix.log",
    filemode="w",
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
    level=logging.INFO,
)

if __name__ == "__main__":
    dam_input = DAMInput.from_folder("data/input")
    dam_input.generate_stix_files("data/output")
