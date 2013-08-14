print "SVN $Id$"

"""
Eigenchannels:
1: Eigenchannels, method from Paulsson and Brandbyge PRB 2007
2: Analyze IETS spectra, Paulsson et al PRL 2008
3: Calculate "bond" currents
"""

import EigenChannels as EC
import NEGF
import SiestaIO as SIO
import MakeGeom as MG
import MiscMath as MM
import WriteNetCDF as NCDF
import numpy as N
import numpy.linalg as LA
import Scientific.IO.NetCDF as NC
import sys, string, struct, glob,  os
from optparse import OptionParser, OptionGroup
import PhysicalConstants as PC
import time

########################################################
##################### Main routine #####################
########################################################
def main(options):
    options.XV = '%s/%s.XV'%(options.head,options.systemlabel)
    options.geom = MG.Geom(options.XV)
    myGF = readHS(options)
    #options.nspin = myGF.HS.nspin
    basis = SIO.BuildBasis(options.XV,options.devSt,options.devEnd,myGF.HS.lasto)
    calcTeig(options,myGF)
    calcIETS(options,myGF,basis)

########################################################
def readHS(options):
    elecL = NEGF.ElectrodeSelfEnergy(options.fnL,options.NA1L,options.NA2L,options.voltage/2.)
    elecR = NEGF.ElectrodeSelfEnergy(options.fnR,options.NA1R,options.NA2R,-options.voltage/2.)
    myGF = NEGF.GF(options.TSHS,elecL,elecR,Bulk=True,DeviceAtoms=[options.devSt, options.devEnd])
    myGF.calcGF(options.energy+options.eta*1.0j,options.kPoint[0:2],ispin=options.iSpin,etaLead=options.etaLead,useSigNCfiles=options.signc)
    return myGF

########################################################
def calcTeig(options,myGF):
    # Matrix to save total and eigenchannel transmissions
    # BEFORE ORTHOGO
    T = myGF.calcT(options.numchan)

    NEGF.SavedSig.close() # Make sure saved Sigma is written to file

    print 'Transmission T(E=%.4f) [Ttot, T1, T2, ... Tn]:'%options.energy
    for t in T:
        print '%.9f '%t,
    print

    # Now orthogonalize in device region
    #HNO = myGF.H.copy() # nonorthogonal device Hamiltonian (needed later)
    myGF.orthogonalize()

    # Check that we get the same transmission:
    T = myGF.calcT(options.numchan)
    print 'Transmission T(E=%.4f) [Ttot, T1, T2, ... Tn]:'%options.energy
    for t in T:
        print '%.9f '%t,
    print

    # Calculate Eigenchannels
    myGF.calcEigChan(options.numchan)
    myGF.trans0 = T[0]

########################################################
def calcIETS(options,myGF,basis):
    # Calculate inelastic scattering rates, total and per eigenchannel

    NCfile = NC.NetCDFFile(options.PhononNetCDF,'r')
    print 'Reading ',options.PhononNetCDF
    
    # Compare coordinates and atomic numbers
    PH_dev = N.array(NCfile.variables['DeviceAtoms'][:])
    PH_xyz = N.array(NCfile.variables['GeometryXYZ'][:])
    PH_anr = N.array(NCfile.variables['AtomNumbers'][:])
    TS_anr = options.geom.anr
    TS_xyz = options.geom.xyz
    print '\nA = %s'%options.PhononNetCDF
    print 'B = %s'%options.XV
    print ' idxA    xA       yA       zA   anrA   ',
    print ' idxB    xB       yB       zB   anrB'
    for i in range(len(PH_dev)):
        s = ('%i'%(PH_dev[0]+i)).rjust(5)
        for j in range(3):
            s += ('%.4f'%(PH_xyz[PH_dev[0]+i,j])).rjust(9)
        s += ('%i'%PH_anr[PH_dev[0]+i]).rjust(4)
        s += '  vs'
        s += ('%i'%(options.devSt+i)).rjust(5)
        for j in range(3):
            s += ('%.4f'%(TS_xyz[options.devSt+i,j])).rjust(9)
        s += ('%i'%TS_anr[options.devSt+i]).rjust(4)
        print s

    # Perform consistency checks for device region in 
    # PH and TS calculations
    print 'Inelastica.calcIETS: Integrity check'
    # - check 1: Matrix sizes
    PH_H0 = N.array(NCfile.variables['H0'][:])
    if N.shape(PH_H0[0])==N.shape(myGF.Gr):
        print '... Check 1 passed: Device orb. space matches'
        check1 = True
    else:
        print '... Check 1 failed: Device orb. space do not match!!!'
        check1 = False
    # - check 2&3: Geometry and atom number
    dist_xyz = 0.0
    dist_anr = 0.0
    for i in range(len(PH_dev)):
        # Geometric distance between atoms
        if i==0:
            # Allow for a global offset of coordinates R
            R = PH_xyz[PH_dev[0]+i]-TS_xyz[options.devSt+i]
        d = PH_xyz[PH_dev[0]+i]-TS_xyz[options.devSt+i] - R
        dist_xyz += N.dot(d,d)**.5
        # Difference between atom numbers
        a = PH_anr[PH_dev[0]+i]-TS_anr[options.devSt+i]
        dist_anr += abs(a)
    if dist_xyz<1e-3:
        print '... Check 2 passed: Atomic coordinates consistent'
        check2 = True
    else:
        print '... Check 2 failed: Atomic coordinates deviate by %.3f Ang!!!'%dist_xyz
        check2 = False
    if dist_anr<1e-3:
        print '... Check 3 passed: Atomic numbers consistent'
        check3 = True
    else:
        print '... Check 3 failed: Atomic numbers inconsistent!!!'
        check3 = False
    if (not check1) or (not check2) or (not check3):
        sys.exit('Inelastica: Error - inconsistency detected for device region.\n')
    
    hw = N.array(NCfile.variables['hw'][:]) 
    # Write matrices to file?
    WriteOrtho = False
    if WriteOrtho:
        ncdf = NCDF.NCfile(options.DestDir+'/ortho.nc')
        ncdf.write(hw,'hw')
    G = myGF.Gr
    G1 = myGF.GamL
    G2 = myGF.GamR
    Gd = dagger(G)
    A1 = myGF.A1
    A2 = myGF.A2
    Us = myGF.Us
    
    bA1 = mm(Gd,G1,G) 

    # Structures to save Power, e-h damping, (non-)Hilbert term
    P1T,P2T = [],[]
    ehDamp1, ehDamp2 = [], []
    nHT,nHTin,nHTel,HT = [],[],[],[]
    
    # Save bond current changes due to inelastic scattering 
    dGnout, dGnin = [], []
    
    for ihw in range(len(hw)):
        SIO.printDone(ihw,len(hw),'IETS FGR')
        M = N.array(NCfile.variables['He_ph'][ihw,options.iSpin,:,:])
        H1=mm(Us,M,Us)
        MA1M, MA2M = mm(H1,A1,H1), mm(H1,A2,H1)
        MAM, MA2mA1M = MA1M+MA2M, MA2M-MA1M
        
        # Write matrices to file?
        if WriteOrtho:
            ncdf.write(H1.real,'ReM%.3i'%ihw)
            ncdf.write(H1.imag,'ImM%.3i'%ihw)
        
        # Cryptic? Changes in G^lesser due to e-ph interaction at high and low energies, i.e.,
        # the changes in occupation due to out(in)-scattering
        tmp1, tmp2 = mm(G,MA2M,A1), mm(G,MA1M,A1)
        dGnout.append(EC.calcCurrent(options,basis,myGF.HNO,mm(Us,-0.5j*(tmp1-dagger(tmp1)),Us)))
        dGnin.append(EC.calcCurrent(options,basis,myGF.HNO,mm(Us,mm(G,MA1M,Gd)-0.5j*(tmp2-dagger(tmp2)),Us)))
        # NB: TF Should one use myGF.HNO or myGF.H above?

        # Power, damping and current rates
        P1T.append(checkImPart(N.trace(mm(MAM,A1+A2))))
        P2T.append(checkImPart(N.trace(mm(MA1M,A2))))        
        ehDamp1.append(checkImPart(N.trace(mm(MA1M,A1))))
        ehDamp2.append(checkImPart(N.trace(mm(MA2M,A2))))
        nHT.append(checkImPart(N.trace(mm(-2*MA2M+1.0j*(mm(MAM,G,G2)-mm(G2,Gd,MAM)),bA1))/2.0))
        nHTin.append(checkImPart(N.trace(mm(-2*MA2M,bA1))/2.0))
        nHTel.append(checkImPart(N.trace(mm(1.0j*(mm(MAM,G,G2)-mm(G2,Gd,MAM)),bA1))/2.0))
        HT.append(checkImPart(N.trace(mm((mm(G2,Gd,MA2mA1M)+mm(MA2mA1M,G,G2)),bA1))))
    # Write matrices to file?
    if WriteOrtho:
        ncdf.write(-1.0*N.array(nHT),'SymTrace')
        ncdf.write(HT,'AsymTrace')
        ncdf.close()
    
    NCfile.close()

    myGF.dGnin, myGF.dGnout = dGnin, dGnout
    myGF.P1T, myGF.P2T = P1T, P2T
    myGF.ehDamp1, myGF.ehDamp2 = ehDamp1, ehDamp2
    myGF.nHT, myGF.HT = nHT, HT
    myGF.nHTin, myGF.nHTel = nHTin, nHTel
    myGF.hw = hw

    unitConv=1.602177e-19/N.pi/1.054572e-34
    print 'checking: nHT',N.array(myGF.nHT)*unitConv # OK
    print 'checking: HT',N.array(myGF.HT) # OK
    
    # Set up grid and Hilbert term
    kT = options.Temp/11604.0 # (eV)

    # Generate grid for numerical integration of Hilbert term    
    max_hw=max(hw)
    max_win=max(-options.minBias,max_hw)+20*kT+4*options.Vrms
    min_win=min(-options.maxBias,-max_hw)-20*kT-4*options.Vrms
    pts=int(N.floor((max_win-min_win)/kT*3))
    Egrid=N.array(range(pts),N.float)/pts*(max_win-min_win)+min_win
    print "LOE: Hilbert integration grid : %i pts [%f,%f]" % (pts,min(Egrid),max(Egrid))
    
    # Calculate the prefactors for the Hilbert and non-Hilbert terms
    # Also calculate the Hilbert transfer of the box on the grid for each mode
    hilb=[] # List of hilbert transforms
    ker=None
    for ii in range(len(hw)):
        hwi=hw[ii]
        tmp=MM.box(hwi,-hwi,Egrid,kT)
        tmp2, ker = MM.Hilbert(tmp,ker)
        hilb.append(tmp2)
        SIO.printDone(ii,len(hw),'LOE : Hilbert transform')
    
    NN = options.biasPoints
    print 'biaspoints',NN

    # Add some points for the Lock in broadening
    approxdV=(options.maxBias-options.minBias)/NN
    NN+=int(((8*options.Vrms)/approxdV)+.5)
    
    Vl=options.minBias-4*options.Vrms+ \
        (options.maxBias-options.minBias+8*options.Vrms)/NN*N.array(range(NN),N.float)
    
    InH=N.zeros((NN,),N.complex) # Non-Hilb-term current
    IH=N.zeros((NN,),N.complex) # Hilb-term current
    Pow=N.zeros((NN,),N.float) # Power
    nPhtot=N.zeros((NN,),N.float) # Number of phonons (sum over modes)
    nPhvsBias=N.zeros((NN,len(hw)),N.float) # Number of phonons
    nPh=N.zeros((len(hw),),N.float)         # Number of phonons                                  

    for iV in range(len(Vl)):
        SIO.printDone(iV,len(Vl),'LOE : Calc current')
        
        InH[iV], IH[iV], Pow[iV] = 0.0, 0.0, 0.0
        V=Vl[iV]
        
        kasse=MM.box(0,-V,Egrid,kT)

        for iOmega in range(len(hw)):
            ihw = hw[iOmega]
            if ihw>options.modeCutoff:
                PV=abs(V)
                
                # Power
                exphw=N.exp(N.clip(ihw/kT,-300,300))
                expV=N.exp(N.clip(PV/kT,-300,300))
                exphwmV=N.exp(N.clip((ihw-PV)/kT,-300,300))
                if ihw/kT>300:
                    mexphw=0.0
                else:
                    mexphw=N.exp(N.clip(-ihw/kT,-300,300))
                if PV/kT>300:
                    mexpV=0.0
                else:
                    mexpV=N.exp(N.clip(-PV/kT,-300,300))

                # Re-written third time lucky? Numerical problems galore!
                if (ihw-PV)/kT>150:
                    tmpheat=0
                else:
                    if abs((ihw-PV)/kT)<1e-3:
                        tmpheat= (2*mexphw*ihw+kT*mexphw**2-kT)/(mexphw**2-1)-\
                                 (PV-ihw)*(4*ihw*mexphw**2+kT*mexphw**4-kT)/(2*kT*(1-mexphw**2)**2)
                    else:
                        tmpheat=(1-mexpV)/(1-mexphw)* \
                                 ((1+mexphw)*(1-mexpV)*ihw-(1-mexphw)*(1+mexpV)*PV)/ \
                                 (exphwmV+mexphw*mexpV-mexpV**2-1)
                        
                heat=tmpheat*myGF.P2T[iOmega]/N.pi # Heating term / (hbar hw)
                
                if options.PhHeating: # Heating?
                    nPh[iOmega]=heat/(ihw*myGF.P1T[iOmega]/N.pi+options.PhExtDamp)+1.0/(exphw-1.0)
                nPhvsBias[iV,iOmega]=nPh[iOmega]
                    
                # Damping term /(hbar hw)
                damp = ihw*(1/(exphw-1)-nPh[iOmega])*myGF.P1T[iOmega]/N.pi
                
                # Power in units of 1/(hbar)
                Pow[iV]=ihw*(heat+damp)
                nPhtot[iV]=nPhtot[iV]+nPh[iOmega]
                tmp=0.0
                if abs(V-ihw)/kT<1e-7:
                    tmp=-kT
                else:
                    tmp=(V-ihw)/(N.exp(N.clip((ihw-V)/kT,-70.0,70.0))-1)
                if abs(V+ihw)/kT<1e-7:
                    tmp+=kT
                else:
                    tmp+=(V+ihw)/(N.exp(N.clip((ihw+V)/kT,-70.0,70.0))-1)
                    InH[iV]+=(tmp-V*nPh[iOmega])*myGF.nHT[iOmega]

                # Finite temp Hilbert
                IH[iV]-=myGF.HT[iOmega]*MM.trapez(Egrid,kasse*hilb[iOmega],\
                                                     equidistant=True)/2
                
        InH[iV]+=V*myGF.trans0 # Last to reduce cancelation errors

    # Get the right units for gamma_eh, gamma_heat
    hbar=1.0545727e-34/1.6021773e-19 # hbar in eV S
    gamma_eh=N.zeros((len(hw),),N.float)
    gamma_heat=N.zeros((len(hw),),N.float)
    for iOmega in range(len(hw)):
        # Units [Phonons per Second per dN where dN is number extra phonons]
        gamma_eh[iOmega]=myGF.P1T[iOmega]*hw[iOmega]/N.pi/hbar
        # Units [Phonons per second per eV [eV-ihw]
        gamma_heat[iOmega]=myGF.P2T[iOmega]/N.pi/hbar

    print 'checking: gamma_eh',gamma_eh # OK
    print 'checking: gamma_heat',gamma_heat # OK

    #hw, T, nHT, HT, lLOE, nPhtot, nPh, = hw, myGF.trans0, myGF.nHT, myGF.HT, [Vl, InH, IH], nPhtot, nPhvsBias
    V, I, dI, ddI, BdI, BddI, NnPhtot,NnPh = Broaden(options,Vl,InH+IH,nPhtot,nPhvsBias)

    print 'checking: BddI',BddI[:10] # OK

    datafile = '%s/%s.IN'%(options.DestDir,options.systemlabel)
    initncfile(datafile,hw)
    writeLOEData2Datafile(datafile,hw,myGF.trans0,nHT,HT)
    writeLOE2ncfile(datafile,hw,nHT,HT,V,I,NnPhtot,NnPh,\
                        dI,ddI,BdI,BddI,gamma_eh,gamma_heat)

    
########################################################
def checkImPart(x):
    if abs(x.imag)>0.0000001:
        print "LOE : Imaginary part (%.3e) too big"%x.imag
        kuk
    return x.real   

########################################################
def writeFGRrates():
    # This does not work at the moment....
    unitConv=1.602177e-19/N.pi/1.054572e-34

    NCfile = NC.NetCDFFile(options.PhononNetCDF,'r')
    print 'Reading ',options.PhononNetCDF

    options.iChan, options.iSide = 0, 2
    outFile = file('%s/%s.IN.FGR'%(options.DestDir,options.systemlabel,'w'))
    outFile.write('Total transmission [in units of (1/s/eV)] : %e\n' % (unitConv*myGF.totTrans.real,))

    tmp=N.sort(abs(N.array(myGF.nHT[:])))
    SelectionMin=tmp[-options.NumPhCurr]        
    
    for ihw in range(len(myGF.hw)):
        SIO.printDone(ihw,len(myGF.hw),'Golden Rate') 
        M = N.array(NCfile.variables['He_ph'][ihw,options.iSpin,:,:])
        rate=N.zeros((len(myGF.ECleft),len(myGF.ECright)),N.float)
        totrate=0.0
        inter,intra = 0.0, 0.0 # splitting total rate in two
        for iL in range(len(myGF.ECleft)):
            for iR in range(len(myGF.ECright)):
                tmp=N.dot(N.conjugate(myGF.ECleft[iL]),mm(M,myGF.ECright[iR]))
                rate[iL,iR]=(2*N.pi)**2*abs(tmp)**2
                totrate+=rate[iL,iR]
                if iL==iR: intra += rate[iL,iR]
                else: inter += rate[iL,iR]

        if abs(myGF.nHT[ihw])>=SelectionMin:
            options.iChan = ihw
            currOut, currIn = IETS.dGnout[ihw], IETS.dGnin[ihw]
            options.iSide = 3
            writeCurrent(currIn)
            options.iSide = 4
            writeCurrent(currOut)
            
        outFile.write('\nPhonon mode %i : %f eV [Rates in units of (1/s/eV)]\n' % (ihw,IETS.hw[ihw]))
        outFile.write('eh-damp : %e (1/s) , heating %e (1/(sV)))\n' % (IETS.P1T[ihw]*unitConv*IETS.hw[ihw],IETS.P2T[ihw]*unitConv))
        outFile.write('eh-damp 1, 2 (MA1MA1, MA2MA2): %e (1/s) , %e (1/(s)))\n' % (IETS.ehDamp1[ihw]*unitConv*IETS.hw[ihw],IETS.ehDamp2[ihw]*unitConv*IETS.hw[ihw]))
        outFile.write('SymI : %e (1/(sV)) , AsymI %e (?))\n' % (IETS.nHT[ihw]*unitConv,IETS.HT[ihw]*unitConv))
        outFile.write('Elast : %e (1/(sV)) , Inelast %e (1/(sV)))\n' % (IETS.nHTel[ihw]*unitConv,IETS.nHTin[ihw]*unitConv))
        outFile.write('down=left EC, right=right EC\n')
        if IETS.P2T[ihw]>0.0:
            if abs(totrate/(IETS.P2T[ihw])-1)<0.05:
                outFile.write('Sum/Tr[MA1MA2] , Tr: %1.3f  %e\n'%(totrate/(IETS.P2T[ihw]),unitConv*IETS.P2T[ihw]))
            else:
                outFile.write('WARNING: !!!! Sum/Tr[MA1MA2] , Tr: %2.2e  %e\n'%(totrate/(IETS.P2T[ihw]),unitConv*IETS.P2T[ihw]))
        else:
            outFile.write(' Tr:  %e\n'%(unitConv*IETS.P2T[ihw]))
        inter = inter/IETS.P2T[ihw]
        intra = intra/IETS.P2T[ihw]
        outFile.write('Interchannel ratio: Sum(inter)/Tr[MA1MA2]      = %.4f \n'%inter)
        outFile.write('Intrachannel ratio: Sum(intra)/Tr[MA1MA2]      = %.4f \n'%intra)
        outFile.write('Inter+intra ratio: Sum(inter+intra)/Tr[MA1MA2] = %.4f \n'%(inter+intra))
        for iL in range(len(IETS.ECleft)):
            for iR in range(len(IETS.ECright)):
                outFile.write('%e ' % (unitConv*rate[iL,iR],))
            outFile.write('\n')
        outFile.close()
        NCfile.close()
                        


################################################################
# Broadening due to Vrms
################################################################

def Broaden(options,VV,II,nPhtot,nPh):
    """
    Broadening corresponding to Lock in measurements for the
    conductance and IETS spectra. Also resample II, nPh and nPhtot
    to match a common voltage list
    """

    II=II.copy()
    II=II.real
    
    # First derivative dI and bias list dV
    dI=(II[1:len(II)]-II[:-1])/(VV[1]-VV[0])
    dV=(VV[1:len(VV)]+VV[:-1])/2
    # Second derivative and bias ddV
    ddI=(dI[1:len(dI)]-dI[:-1])/(VV[1]-VV[0])
    ddV=(dV[1:len(dV)]+dV[:-1])/2

    # Modulation amplitude
    VA=N.sqrt(2.0)*options.Vrms 

    # New bias ranges for broadening
    tmp=int(N.floor(VA/(dV[1]-dV[0]))+1)
    BdV=dV[tmp:-tmp]
    BddV=ddV[tmp:-tmp]

    # Initiate derivatives
    BdI=0*BdV
    BddI=0*BddV
    
    # Calculate first derivative with Vrms broadening
    for iV, V in enumerate(BdV):
        wt=(N.array(range(200))/200.0-0.5)*N.pi
        VL=V+VA*N.sin(wt)
        dIL=MM.interpolate(VL,dV,dI)
        BdI[iV]=2/N.pi*N.sum(dIL*(N.cos(wt)**2))*(wt[1]-wt[0])

    # Calculate second derivative with Vrms broadening    
    for iV, V in enumerate(BddV):
        wt=(N.array(range(200))/200.0-0.5)*N.pi
        VL=V+VA*N.sin(wt)
        ddIL=MM.interpolate(VL,ddV,ddI)
        BddI[iV]=8.0/3.0/N.pi*N.sum(ddIL*(N.cos(wt)**4))*(wt[1]-wt[0])

    # Reduce to one voltage grid
    NN=options.biasPoints 
    V=options.minBias+(options.maxBias-options.minBias)/NN*N.array(range(NN)) 

    NI=MM.interpolate(V,VV,II)
    NdI=MM.interpolate(V,dV,dI)
    NddI=MM.interpolate(V,ddV,ddI)
    NBdI=MM.interpolate(V,BdV,BdI)
    NBddI=MM.interpolate(V,BddV,BddI)
    NnPhtot=MM.interpolate(V,VV,nPhtot)
    NnPh=N.zeros((len(V),len(nPh[0,:])),N.float)
    for ii in range(len(nPh[0,:])):
        NnPh[:,ii]=MM.interpolate(V,VV,nPh[:,ii])
    
    return V, NI ,NdI, NddI, NBdI, NBddI, NnPhtot, NnPh

################################################################
# Output to NetCDF file
################################################################

def initncfile(filename,hw):
    'Initiate netCDF file'
    print 'Inelastica: Initializing nc-file'
    ncfile = NC.NetCDFFile(filename+'.nc','w','Created '+time.ctime(time.time()))
    ncfile.title = 'Inelastica Output'
    ncfile.version = 1
    ncfile.createDimension('Nph',len(hw))
    ncfile.createDimension('Bias',None)
    tmp = ncfile.createVariable('IelasticL','d',('Bias',))
    tmp.units = 'Conductance quantum'
    tmp1 = ncfile.createVariable('IelasticR','d',('Bias',))
    tmp1.units = 'Conductance quantum'
    tmp2 = ncfile.createVariable('IinelasticL','d',('Bias',))
    tmp2.units = 'Conductance quantum'
    tmp3 = ncfile.createVariable('IinelasticR','d',('Bias',))
    tmp3.units = 'Conductance quantum'
    tmp4 = ncfile.createVariable('Bias','d',('Bias',))
    tmp4.units = 'V'
    nchw = ncfile.createVariable('hw','d',('Nph',))
    nchw[:] = N.array(hw)
    nchw.units = 'eV'
    ncfile.close()
    
def writeLOE2ncfile(filename,hw,nHT,HT,V,I,nPhtot,nPh,\
                     dI,ddI,BdI,BddI,gamma_eh,gamma_heat):
    'Write LOE data to netCDF file'
    print 'Inelastica: Write LOE data to nc-file'
    ncfile = NC.NetCDFFile(filename+'.nc','a')
    ncfile.createDimension('LOE_V',len(V))
    tmp=ncfile.createVariable('LOE_V','d',('LOE_V',))
    tmp[:]=N.array(V)
    tmp.units='V'
    tmp=ncfile.createVariable('LOE_IETS','d',('LOE_V',))
    tmpn=BddI/BdI
    tmp[:]=N.array(tmpn.real)
    tmp.units='Broadened ddI/dI [1/V]'
    tmp=ncfile.createVariable('LOE_dI','d',('LOE_V',))
    tmp[:]=N.array(dI.real)
    tmp.units='dI LOE, G0'
    tmp=ncfile.createVariable('LOE_ddI','d',('LOE_V',))
    tmp[:]=N.array(ddI.real)
    tmp.units='ddI LOE, G0/V'
    tmp=ncfile.createVariable('LOE_BdI','d',('LOE_V',))
    tmp[:]=N.array(BdI.real)
    tmp.units='Broadened dI LOE, G0'
    tmp=ncfile.createVariable('LOE_BddI','d',('LOE_V',))
    tmp[:]=N.array(BddI.real)
    tmp.units='Broadened ddI LOE, G0/V'
    tmp=ncfile.createVariable('LOE_I','d',('LOE_V',))
    tmp[:]=N.array(I.real)
    tmp.units='G0 V'
    tmp=ncfile.createVariable('LOE_tot_nPh','d',('LOE_V',))
    tmp[:]=N.array(nPhtot.real)
    tmp.units='Total number of phonons '
    tmp=ncfile.createVariable('LOE_nPh','d',('LOE_V','Nph'))
    tmp[:]=N.array(nPh.real)
    tmp.units='Number of phonons'
    tmp=ncfile.createVariable('LOE_gamma_eh','d',('Nph',))
    tmp[:]=N.array(gamma_eh)
    tmp.units='e-h damping [*deltaN=1/Second]'
    tmp=ncfile.createVariable('LOE_gamma_heat','d',('Nph',))
    tmp[:]=N.array(gamma_heat)
    tmp.units='Phonon heating [*(bias-hw) (eV) = 1/Second]'
    unitConv=1.602177e-19/N.pi/1.054572e-34
    ncTotR = ncfile.createVariable('LOE_ISymTr','d',('Nph',))
    ncTotR[:] = N.array(nHT)*unitConv
    ncTotR.units = 'Trace giving Symmetric current contribution (same units as eigenchannels [1/s/eV])'
    ncTotL = ncfile.createVariable('LOE_IAsymTr','d',('Nph',))
    ncTotL[:] = N.array(HT)
    ncTotL.units = 'Trace giving Asymmetric current contribution'
    
    ncfile.close()
    
def writeLOEData2Datafile(file,hw,T,nHT,HT):
    f = open(file,'a')
    f.write("## Almost First Order Born Approximation (kbT=0)\n")
    f.write("## hw(eV)      Trans        non-H-term (e/pi/hbar)   H-term\n")
    for ii in range(len(hw)):
        f.write("## %e %e %e %e\n" % (hw[ii],T,nHT[ii],HT[ii]))
    f.write("\n")
    f.close()

def writeData2ncfile(filename,dict,ibias):
    'Append data to netCDF file'
    print 'Inelastica: Writing SCBA data to nc-file'
    bias = dict['bias']
    IelasticL = dict['NCL'] # Elastic current [Units, e/Pi/hbar, i.e.,
    #                         energy in eV, bias in V -> Current * 77 muA]
    IelasticR = (-dict['NCR'])
    IinelasticL = (dict['ICL']) # Left Current
    IinelasticR = (-dict['ICR']) # Right Current
    Nph=dict['nPh'] # Number of phonons
    # Add new data (some nicer way should exist)
    
    ncfile = NC.NetCDFFile(filename+'.nc','a')
    ncIelasticL = ncfile.variables['IelasticL']
    ncIelasticR = ncfile.variables['IelasticR']
    ncIinelasticL = ncfile.variables['IinelasticL']
    ncIinelasticR = ncfile.variables['IinelasticR']
    ncBias = ncfile.variables['Bias']
    ncNph = ncfile.variables['SCBA_nPh']

    tmp = ncBias[:]
    ncBias[len(tmp)] = bias

    tmp = ncIelasticL[:]
    ncIelasticL[len(tmp)]=IelasticL
    ncIelasticR[len(tmp)]=IelasticR
    ncIinelasticL[len(tmp)]=IinelasticL
    ncIinelasticR[len(tmp)]=IinelasticR
    ncNph[len(tmp),:]=Nph
    ncfile.close()

def writeData2Datafile(file,dict,hw):
    c1 = dict['bias']
    c2 = dict['NCL'] # Currents in units of e/pi/hbar*energy, i.e.,
    #                  G=77 muA/V * dI/dV if energy [eV], bias [V]
    c3 = (dict['ICL']-dict['ICR'])/2 # Average of left and right
    c4 = dict['NPL']+dict['NPR']
    c5 = dict['IPL']+dict['IPR']
    data = [c1,c2,c3,c4,c5]
    form = '%e   %e   %e   %e   %e   '
    for i in range(len(hw)):
        data.append(dict['nPh'][i])
        form += '%f   '
    form += '\n'
    data = tuple(data)
    f = open(file,'a')
    f.write(form %data)
    f.close()




################# Math helpers ################################
mm = MM.mm
outerAdd = MM.outerAdd
dagger = MM.dagger
    
##################### Start main routine #####################

if __name__ == '__main__':
    main()

