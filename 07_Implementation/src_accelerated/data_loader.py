from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd


class ProfileData:
    def __init__(self, csv_load: Path, csv_pv: Path):
                
        df_load = pd.read_csv(csv_load)
        df_pv = pd.read_csv(csv_pv)
        
        required_load_columns = {"timestamp", "bus_id", "p_kw", "q_kvar"}
        required_pv_columns = {"timestamp", "bus_id", "p_kw", "q_kvar"}

        if not required_load_columns.issubset(df_load.columns):
            raise ValueError("Load CSV is missing required columns.")

        if not required_pv_columns.issubset(df_pv.columns):
            raise ValueError("PV CSV is missing required columns.")
        
        if df_load.duplicated(subset=["timestamp", "bus_id"]).any():
            raise ValueError("Duplicate load rows found.")

        if df_pv.duplicated(subset=["timestamp", "bus_id"]).any():
            raise ValueError("Duplicate PV rows found.")
        
        df_load = df_load.sort_values(["timestamp", "bus_id"])
        df_pv = df_pv.sort_values(["timestamp", "bus_id"])
        
        load_timestamps = set(df_load["timestamp"].unique())
        pv_timestamps = set(df_pv["timestamp"].unique())

        if load_timestamps != pv_timestamps:
            raise ValueError("Load and PV timestamps do not match.")

        # Convert timestamp strings into datetime objects
        df_load["timestamp"] = pd.to_datetime(df_load["timestamp"])
        df_pv["timestamp"] = pd.to_datetime(df_pv["timestamp"])

        # Unique simulation timestamps
        self.timestamps = sorted(df_load["timestamp"].unique())

        # Dictionaries: bus_id -> values over time
        self.load_p_kw = {}
        self.load_q_kvar = {}
        self.pv_p_kw = {}
        self.pv_q_kvar = {}

        for bus_id, group in df_load.groupby("bus_id"):
            self.load_p_kw[int(bus_id)] = group["p_kw"].tolist()
            self.load_q_kvar[int(bus_id)] = group["q_kvar"].tolist()

        for bus_id, group in df_pv.groupby("bus_id"):
            self.pv_p_kw[int(bus_id)] = group["p_kw"].tolist()
            self.pv_q_kvar[int(bus_id)] = group["q_kvar"].tolist()

        if len(self.timestamps) < 2:
            raise ValueError("Profile must contain at least two timestamps.")
                
        for i in range(1, len(self.timestamps)):
            difference = self.timestamps[i] - self.timestamps[i - 1]
            hours = difference.total_seconds() / 3600

            if hours != 1.0:
                raise ValueError("Profile timestamps must be hourly.")
            
        self.dt_hours = 1.0

class ProfileSlice:
    def __init__(self, profile_data: ProfileData, index: int):

        if index < 0 or index >= len(profile_data.timestamps):
            raise IndexError("Profile index out of range.")

        self.timestamp = profile_data.timestamps[index]

        self.p_load_kw = {
            bus_id: values[index]
            for bus_id, values in profile_data.load_p_kw.items()
        }

        self.q_load_kvar = {
            bus_id: values[index]
            for bus_id, values in profile_data.load_q_kvar.items()
        }

        self.p_pv_kw = {
            bus_id: values[index]
            for bus_id, values in profile_data.pv_p_kw.items()
        }

        self.q_pv_kvar = {
            bus_id: values[index]
            for bus_id, values in profile_data.pv_q_kvar.items()
        }

def profile_at(profile_data: ProfileData, index: int) -> ProfileSlice:
    return ProfileSlice(profile_data, index)

if __name__ == "__main__":
    # Example usage
    csv_load_path = Path("C:\\Users\\ISLAHI\\Downloads\\load_profile.csv")
    csv_pv_path = Path("C:\\Users\\ISLAHI\\Downloads\\pv_profile.csv")
    profile_data = ProfileData(csv_load_path, csv_pv_path)
    '''
    print(type(profile_data.load_p_kw[0]))
    
    for i in range(len(profile_data.timestamp)):
        print(i, profile_data.timestamp[i], profile_data.load_p_kw[i], profile_data.load_q_kvar[i], profile_data.pv_p_kw[i], profile_data.pv_q_kvar[i])
    
    print(profile_data.timestamps)
    print(profile_data.load_p_kw)
    print(profile_data.pv_p_kw)
    '''
    print(pd.read_csv(csv_load_path))  
    print(profile_data.load_p_kw[2])
    print(profile_data.pv_p_kw[3])
    
    slice_0 = profile_at(profile_data, 0)
    print(slice_0.timestamp)
    print(slice_0.p_load_kw)
    print(slice_0.p_pv_kw)