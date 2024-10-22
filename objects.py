from pydantic import BaseModel
from typing import List, Optional, Union
from pathlib import Path
import logging
from enum import IntEnum

X_UNDEFINED = -9999


class CSVBasedObect(BaseModel):
    columns: List[str] = []
    data: List[List[str]] = []

    @classmethod
    def read(cls, filename: str) -> "CSVBasedObect":
        result = CSVBasedObect()
        lines = open(filename, "r").readlines()
        result.columns = [s.strip().replace(" ", "_") for s in lines[0].split(";")]

        for line in [l for l in lines[1:] if len(l.strip()) > 0]:
            result.data.append([s.strip() for s in line.split(";")])

        return result

    @property
    def length(self) -> int:
        return len(self.data)

    def column(self, header) -> Optional[List[str]]:
        i = self.columns.index(header)
        if i < 0:
            return None
        return [d[i] for d in self.data]

    def column_index(self, header) -> Optional[int]:
        i = self.columns.index(header)
        if i < 0:
            return None
        else:
            return i


class Soil(BaseModel):
    name: str
    yd: float
    ys: float
    c: float
    phi: float


class Combination(BaseModel):
    soilprofile_id_crest: str = ""
    soilprofile_id_toe: str = ""
    surfaceline_id: str = ""
    soilgeometry2D_name: str = ""


class SlopeLayer(BaseModel):
    surfaceline_id: str = ""
    slope_layer_thickness: float


class SoilProfileLayer(BaseModel):
    top: float
    bottom: float
    soil_name: str


class SoilProfile(BaseModel):
    id: str
    layers: List[SoilProfileLayer] = []

    def sort(self) -> None:
        self.layers = sorted(self.layers, key=lambda x: x.top, reverse=True)


class SurfaceLinePoint(BaseModel):
    x: float
    y: float
    z: float


class SurfaceLine(BaseModel):
    id: str
    points: List[SurfaceLinePoint] = []

    x_binnenkruin: float = X_UNDEFINED
    x_binnenteen: float = X_UNDEFINED


class Segment(BaseModel):
    pass


class Location(BaseModel):
    pass


class DAMInput(BaseModel):
    combinations: List[Combination] = []
    slopelayers: List[SlopeLayer] = []
    soilprofiles: List[SoilProfile] = []
    surfacelines: List[SurfaceLine] = []
    segments: List[Segment] = []
    locations: List[Location] = []
    soils: List[Soil] = []

    @classmethod
    def from_folder(cls, folder: str) -> Optional["DAMInput"]:
        result = DAMInput()
        try:
            combinations = CSVBasedObect.read(Path(folder) / "combinationfile.csv")
            slopelayers = CSVBasedObect.read(Path(folder) / "slopelayers.csv")
            soilprofiles = CSVBasedObect.read(Path(folder) / "soilprofiles.csv")
            charpoints = CSVBasedObect.read(Path(folder) / "characteristicpoints.csv")
            segments = CSVBasedObect.read(Path(folder) / "segments.csv")
            locations = CSVBasedObect.read(Path(folder) / "locations.csv")
        except Exception as e:
            raise ValueError(f"Fout bij het lezen van de invoergegevens; '{e}'")

        ################
        # COMBINATIONS #
        ################
        for d in combinations.data:
            result.combinations.append(
                Combination(
                    soilprofile_id_crest=d[
                        combinations.column_index("soilprofile_id_crest")
                    ],
                    soilprofile_id_toe=d[
                        combinations.column_index("soilprofile_id_toe")
                    ],
                    surfaceline_id=d[combinations.column_index("surfaceline_id")],
                    soilgeometry2D_name=d[
                        combinations.column_index("soilgeometry2D_name")
                    ],
                )
            )

        ################
        # SOILPROFILES #
        ################
        unique_ids = list(
            set(
                [
                    d[soilprofiles.column_index("soilprofile_id")]
                    for d in soilprofiles.data
                ]
            )
        )
        for id in unique_ids:
            soilprofile = SoilProfile(id=id)

            layers = [
                d
                for d in soilprofiles.data
                if d[soilprofiles.column_index("soilprofile_id")] == id
            ]

            for layer in layers:
                soilprofile.layers.append(
                    SoilProfileLayer(
                        top=float(layer[soilprofiles.column_index("top_level")]),
                        bottom=float(layer[soilprofiles.column_index("bottom_level")]),
                        soil_name=layer[soilprofiles.column_index("soil_name")],
                    )
                )

            # just to be sure
            soilprofile.sort()
            result.soilprofiles.append(soilprofile)

        ################
        # SURFACELINES #
        ################
        lines = open(Path(folder) / "surfacelines.csv").readlines()
        for line in lines[1:]:
            args = [s.strip() for s in line.split(";")]
            xs = [float(a) for a in args[1 : len(args) : 3]]
            ys = [float(a) for a in args[2 : len(args) : 3]]
            zs = [float(a) for a in args[3 : len(args) : 3]]

            result.surfacelines.append(
                SurfaceLine(
                    id=args[0],
                    points=[
                        SurfaceLinePoint(x=d[0], y=d[1], z=d[2])
                        for d in zip(xs, ys, zs)
                    ],
                )
            )

        #############################
        # ADD CHARACTERISTIC POINTS #
        #############################
        for d in charpoints.data:
            location_id = d[charpoints.column_index("LOCATIONID")]
            x_binnenkruin = d[charpoints.column_index("X_Kruin_binnentalud")]
            x_binnenteen = d[charpoints.column_index("X_Teen_dijk_binnenwaarts")]
            result.add_charpoints(location_id, x_binnenkruin, x_binnenteen)

        ###################
        # SOIL PARAMETERS #
        ###################
        lines = open(Path(folder) / "soilparameters.csv").readlines()
        for line in lines[1:]:
            args = [s.strip() for s in line.split(";")]
            result.soils.append(
                Soil(
                    name=args[0],
                    yd=float(args[1]),
                    ys=float(args[2]),
                    c=float(args[3]),
                    phi=float(args[4]),
                )
            )

        ################
        # SLOPE LAYERS #
        ################
        for d in slopelayers.data:
            result.slopelayers.append(
                SlopeLayer(
                    surfaceline_id=d[slopelayers.column_index("surfaceline_id")],
                    slope_layer_thickness=float(
                        d[slopelayers.column_index("slope_layer_thickness")]
                    ),
                )
            )

        return result

    def add_charpoints(
        self, location_id: str, x_binnenkruin: float, x_binnenteen: float
    ) -> None:
        for i in range(len(self.surfacelines)):
            if self.surfacelines[i].id == location_id:
                self.surfacelines[i].x_binnenkruin = x_binnenkruin
                self.surfacelines[i].x_binnenteen = x_binnenteen
                return

        raise ValueError(
            f"Geen karakteristieke punten gevonden voor surfaceline '{location_id}'"
        )

    def generate_stix_files(self, output_path: Union[str, Path]) -> None:
        Path(output_path).mkdir(parents=True, exist_ok=True)
        for combination in self.combinations:
            pass
            # print(combination)

    # )
    # # soilprofile_id_toe = self.combinations.data[i][
    #     self.combinations.column_index("soilprofile_id_toe")
    # ]
    # surfaceline_id = self.combinations.data[i][
    #     self.combinations.column_index("surfaceline_id")
    # ]
    # soilgeometry2D_name = self.combinations.data[i][
    #     self.combinations.column_index("soilgeometry2d_name")
    # ]
    # print(
    #     soilprofile_id_crest,
    #     soilprofile_id_toe,
    #     surfaceline_id,
    #     soilgeometry2D_name,
    # )


if __name__ == "__main__":
    logging.basicConfig(
        filename="dam2stix.log",
        filemode="w",
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
        level=logging.INFO,
    )

    dam_input = DAMInput.from_folder("data/input")
    print(dam_input)
    # dam_input.generate_stix_files("data/output")
