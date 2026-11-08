"""CLI utility: pre-aggregate distributed bus loads for any network in ZIP."""
import argparse
from data_engine import export_prepared_zip

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('distributed_zip',help='ZIP from GoiEner Load Distributor')
    parser.add_argument('-o','--output',default='prepared_plots')
    args=parser.parse_args()
    for path in export_prepared_zip(args.distributed_zip,args.output):
        print('Wrote',path)
