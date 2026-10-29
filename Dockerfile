FROM ubuntu:24.04

RUN apt-get update && apt-get install -y g++ python3 python3-dev pkg-config cmake git ccache wget bzip2 python3-pandas python3-matplotlib python3-scipy && rm -rf /var/lib/apt/lists/*

WORKDIR /ns3

RUN wget https://www.nsnam.org/releases/ns-allinone-3.48.tar.bz2 && echo "62fa2080187dcf2f7de8ccde149575fa1227f859  ns-allinone-3.48.tar.bz2" | sha1sum -c - && tar -xjf ns-allinone-3.48.tar.bz2 && rm ns-allinone-3.48.tar.bz2

WORKDIR /ns3/ns-allinone-3.48/ns-3.48

CMD ["/bin/bash"]
